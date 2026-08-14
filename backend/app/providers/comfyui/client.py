"""ComfyUIClient (mvp-spec §64): thin HTTP + WebSocket client for the ComfyUI server API.

Studio only ever speaks Studio contracts outward; this client translates
ComfyUI protocol → Studio progress events (contract §112-113: never leak node_id etc. to frontend).
"""

from __future__ import annotations

import asyncio
import json
import uuid

import httpx

from app.core.config import settings
from app.core.errors import ComfyUIError, ProviderUnavailableError
from app.core.logging import get_logger

logger = get_logger("comfyui.client")


class ComfyUIClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.comfyui_url).rstrip("/")
        self._client_id = str(uuid.uuid4())

    # --- health ---

    async def health_check(self) -> tuple[bool, float | None]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                start = asyncio.get_event_loop().time()
                resp = await client.get(f"{self.base_url}/system_stats")
                latency = (asyncio.get_event_loop().time() - start) * 1000
                return resp.status_code == 200, round(latency, 1)
        except Exception:  # noqa: BLE001
            return False, None

    # --- queue ---

    async def queue_prompt(self, workflow: dict) -> str:
        """Submit API-format workflow; returns prompt_id."""
        payload = {"prompt": workflow, "client_id": self._client_id}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(f"{self.base_url}/prompt", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data.get("prompt_id", "")
        except httpx.HTTPStatusError as exc:
            raise ComfyUIError(f"ComfyUI rejected workflow: {exc.response.text[:300]}") from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailableError(f"ComfyUI unreachable at {self.base_url}: {exc}") from exc

    async def get_history(self, prompt_id: str) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.base_url}/history/{prompt_id}")
                resp.raise_for_status()
                history = resp.json()
                return history.get(prompt_id)
        except Exception:  # noqa: BLE001
            return None

    async def get_outputs(self, prompt_id: str) -> list[dict]:
        """Resolve output image refs from history: [{filename, subfolder, type}]."""
        history = await self.get_history(prompt_id)
        if not history:
            return []
        outputs: list[dict] = []
        for node_output in history.get("outputs", {}).values():
            for image in node_output.get("images", []):
                if image.get("type") == "output":
                    outputs.append(image)
        return outputs

    async def download_output(self, image: dict, destination: str) -> str:
        """Download one output image to destination (absolute path)."""
        params = {
            "filename": image["filename"],
            "subfolder": image.get("subfolder", ""),
            "type": image.get("type", "output"),
        }
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(f"{self.base_url}/view", params=params)
                resp.raise_for_status()
                with open(destination, "wb") as f:
                    f.write(resp.content)
                return destination
        except httpx.TransportError as exc:
            raise ProviderUnavailableError(f"ComfyUI output download failed: {exc}") from exc

    async def upload_image(self, file_path: str, subfolder: str = "") -> dict:
        """Upload a reference image for ControlNet/IPAdapter-style workflows."""
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                with open(file_path, "rb") as f:
                    resp = await client.post(
                        f"{self.base_url}/upload/image",
                        files={"image": f},
                        data={"overwrite": "true", "subfolder": subfolder},
                    )
                resp.raise_for_status()
                return resp.json()
        except httpx.TransportError as exc:
            raise ProviderUnavailableError(f"ComfyUI image upload failed: {exc}") from exc

    async def cancel(self, prompt_id: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(f"{self.base_url}/interrupt", json={})
                await client.post(f"{self.base_url}/queue", json={"delete": [prompt_id]})
        except Exception:  # noqa: BLE001
            logger.warning("comfyui cancel best-effort failed for %s", prompt_id)

    # --- websocket monitoring ---

    async def monitor(self, prompt_id: str, on_progress, on_done, on_error, timeout: float = 900.0) -> None:
        """Stream ComfyUI WS events → Studio progress callbacks. Blocks until done/error/timeout."""
        ws_url = f"ws://{self._host_port()}/ws?clientId={self._client_id}"
        try:
            import websockets

            async with websockets.connect(ws_url, max_size=None, open_timeout=15) as ws:
                async with asyncio.timeout(timeout):
                    while True:
                        message = await ws.recv()
                        if isinstance(message, bytes):
                            continue
                        data = json.loads(message)
                        msg_type = data.get("type")
                        if msg_type == "progress":
                            on_progress(data["data"]["value"], data["data"]["max"])
                        elif msg_type == "executing":
                            node = data.get("data", {}).get("node")
                            if node is None:
                                on_done()
                                return
                            if node == "14":
                                on_progress(99, "saving")
                        elif msg_type == "executed":
                            on_progress(100, "saving")
                        elif msg_type == "execution_error":
                            error = data.get("data", {}).get("exception_message") or "ComfyUI execution error"
                            on_error(error)
                            return
                        elif msg_type == "execution_interrupted":
                            on_error("Generation interrupted.")
                            return
        except asyncio.TimeoutError:
            on_error("ComfyUI generation timed out.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("ws monitor ended for %s: %s", prompt_id, exc)
            # connection lost → fall back to history polling for final state
            await self._poll_history_fallback(prompt_id, on_done, on_error)

    async def _poll_history_fallback(self, prompt_id: str, on_done, on_error) -> None:
        for _ in range(20):
            await asyncio.sleep(1)
            outputs = await self.get_outputs(prompt_id)
            if outputs:
                on_done()
                return
        on_error("ComfyUI connection lost and history never completed.")

    def _host_port(self) -> str:
        url = self.base_url.replace("http://", "").replace("https://", "")
        return url.split("/")[0]
