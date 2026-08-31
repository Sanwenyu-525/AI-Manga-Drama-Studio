"""ComfyUIClient (mvp-spec §64): thin HTTP + WebSocket client for the ComfyUI server API.

Studio only ever speaks Studio contracts outward; this client translates
ComfyUI protocol → Studio progress events (contract §112-113: never leak node_id etc. to frontend).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

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

    async def get_models(self) -> tuple[bool, list[str]]:
        """List checkpoint filenames via GET /object_info/CheckpointLoaderSimple.

        Returns (reachable, models) — never raises. trust_env=False：base_url 是
        用户显式配置的本机端点，跟随系统代理会把回环地址劫持成 502（同 llm 探测）。
        """
        reachable, catalog = await self.get_catalog()
        return reachable, catalog.get("checkpoints", [])

    _LOADER_NODE_TO_SLOT: dict[str, str] = {
        # Probe 时投影到的枚举槽位：设置页/API 按架构分类展示。
        "CheckpointLoaderSimple": "checkpoints",
        "UNETLoader": "unets",
        "CLIPLoader": "clips",
        "DualCLIPLoader": "clips",
        "VAELoader": "vaes",
    }

    async def get_catalog(self) -> tuple[bool, dict[str, list[str]]]:
        """Sprint 05 (P2-1): per-architecture model catalog from /object_info.

        Queries the known loader nodes in parallel and maps each node's model-name
        enum (the first list-of-strings item in its required input) into a catalog
        slot. Legacy /comfyui/models stays as the checkpoints-only view; the UI can
        consume the fuller catalog (DiT unets for Z-Image etc. — Sprint 04 evidence:
        UNETLoader-loaded z_image_turbo.int8 never appeared in the old endpoint).

        `reachable` is True when the server answered at least one probe (HTTP-level
        response counts, preserving the legacy non-200 => reachable semantic); it is
        False only when every probe hit a transport error. Never raises.
        """
        try:
            async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
                async def _one(node: str) -> tuple[bool, list[str]]:
                    try:
                        r = await client.get(f"{self.base_url}/object_info/{node}")
                    except Exception:  # noqa: BLE001  — transport error on this node
                        return False, []
                    if r.status_code != 200:
                        return True, []
                    try:
                        info = r.json().get(node, {})
                        required = (info.get("input") or {}).get("required") or {}
                        for raw in required.values():
                            if not isinstance(raw, list) or not raw:
                                continue
                            # ComfyUI 枚举两种形态：[["a","b"], {meta}] 或 ["a","b"]
                            first = raw[0]
                            if isinstance(first, list) and first and isinstance(first[0], str):
                                names = first
                            elif isinstance(raw, list) and isinstance(raw[0], str):
                                names = raw
                            else:
                                continue
                            return True, [n for n in names if isinstance(n, str)]
                    except (ValueError, KeyError, TypeError, IndexError):
                        pass
                    return True, []

                results = await asyncio.gather(
                    *[asyncio.create_task(_one(n)) for n in self._LOADER_NODE_TO_SLOT]
                )
        except Exception:  # noqa: BLE001
            return False, {}

        reachable = any(ok for ok, _ in results)
        if not reachable:
            return False, {}
        catalog: dict[str, list[str]] = {slot: [] for slot in set(self._LOADER_NODE_TO_SLOT.values())}
        for node, (_, names) in zip(self._LOADER_NODE_TO_SLOT, results, strict=True):
            catalog[self._LOADER_NODE_TO_SLOT[node]].extend(names)
        return True, {slot: sorted(set(v)) for slot, v in catalog.items()}

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
                with open(destination, "wb") as f:  # noqa: ASYNC230 — local desktop file IO is acceptable for MVP
                    f.write(resp.content)
                return destination
        except httpx.TransportError as exc:
            raise ProviderUnavailableError(f"ComfyUI output download failed: {exc}") from exc

    async def upload_image(self, file_path: str, subfolder: str = "", filename: str | None = None) -> dict:
        """Upload a reference image for ControlNet/IPAdapter-style workflows.

        filename: optional multipart filename override (M1: the provider passes a
        uuid-prefixed name so the ComfyUI-side reference file is collision-free).
        HTTP errors raise ComfyUIError (same wrapping as queue_prompt) and transport
        errors ProviderUnavailableError, so callers fail the generation honestly.
        """
        upload_name = filename or Path(file_path).name
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                with open(file_path, "rb") as f:  # noqa: ASYNC230 — local desktop file IO is acceptable for MVP
                    resp = await client.post(
                        f"{self.base_url}/upload/image",
                        files={"image": (upload_name, f)},
                        data={"overwrite": "true", "subfolder": subfolder},
                    )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            raise ComfyUIError(f"ComfyUI image upload failed: {exc.response.text[:300]}") from exc
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

    async def monitor(self, prompt_id: str, on_progress, on_done, on_error, timeout_seconds: float = 900.0) -> None:
        """Stream ComfyUI WS events → Studio progress callbacks. Blocks until done/error/timeout."""
        ws_url = f"ws://{self._host_port()}/ws?clientId={self._client_id}"
        try:
            import websockets

            async with websockets.connect(ws_url, max_size=None, open_timeout=15) as ws:
                async with asyncio.timeout(timeout_seconds):
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
                            # P1-E2-T01: no hardcoded output node id — "executed" /
                            # "execution_error" events carry the final state.
                        elif msg_type == "executed":
                            on_progress(100, "saving")
                        elif msg_type == "execution_error":
                            error = data.get("data", {}).get("exception_message") or "ComfyUI execution error"
                            on_error(error)
                            return
                        elif msg_type == "execution_interrupted":
                            on_error("Generation interrupted.")
                            return
        except TimeoutError:
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
