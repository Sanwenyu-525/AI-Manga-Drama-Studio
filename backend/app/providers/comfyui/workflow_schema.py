"""WorkflowSchema (P4-T005) — declarative logical-parameter contract (backend-architecture §42).

Studio's layer never needs to understand KSampler/CLIP/VAE/ControlNet nodes or any
ComfyUI node_id. Instead, each workflow is declared as an ordered set of *logical*
parameters: a Studio name mapped to a $PLACEHOLDER token in the template, with a
value type, an optional default and (for numerics) a valid range.

Two kinds of validation live here:

1. Template validation (preflight): every placeholder token that appears in the
   template MUST be declared in the schema (unknown token → error), and every schema
   param marked required must have its placeholder present in the template. This keeps
   the existing REQUIRED_PLACEHOLDERS semantics but turns it into a schema-derived rule
   instead of a hardcoded tuple.

2. Build validation: before substitution, the request values are type/range checked and
   surfaced as ValidationError (422) — e.g. width/height outside 64..4096, or an illegal
   seed. MVP image parameters are instantiated; video-only parameters (duration,
   resolution) are declared as reserved but never materialized in the image path.

The mapper (workflow_mapper.build) consults this schema so it no longer hand-writes the
values dict.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Literal

from app.core.errors import ValidationError

# --- allowed ranges / defaults ---------------------------------------------------------

IMAGE_MIN_DIMENSION = 64
IMAGE_MAX_DIMENSION = 4096
DEFAULT_IMAGE_WIDTH = 512
DEFAULT_IMAGE_HEIGHT = 912
SEED_MIN = 0
SEED_MAX = 2**31 - 1
SEED_DEFAULT_RANGE = 2**31  # random.seed fallback range
# 默认 checkpoint 文件名（image.json 的 checkpoint 覆盖层的回落值；单一事实源在此）。
DEFAULT_CHECKPOINT = "sd_xl_base_1.0.safetensors"


@dataclass(frozen=True)
class WorkflowParam:
    """One declarative logical parameter for a WorkflowSchema.

    - name: Studio-side logical name (never a node id / node slot).
    - placeholder: the $TOKEN in the template this param maps to.
    - value_type: str | int | list[str] — drives build-time type coercion.
    - required: the placeholder MUST appear in the template (preflight).
    - default / min / max: build-time defaults and (for ints) range bounds.
    - reserved: declared for a future media type (video) but not instantiated in MVP.
    """

    name: str
    placeholder: str
    value_type: Literal["str", "int", "list[str]"] = "str"
    required: bool = False
    default: Any = None
    min: int | None = None
    max: int | None = None
    reserved: bool = False
    description: str = field(default="")


# Canonical image-parameter schema — the single source of truth for injection.
IMAGE_PARAMETERS: tuple[WorkflowParam, ...] = (
    WorkflowParam("prompt", "$PROMPT", "str", required=True,
                  description="Positive prompt."),
    WorkflowParam("negative_prompt", "$NEGATIVE_PROMPT", "str", default="",
                  description="Negative prompt (optional)."),
    WorkflowParam("seed", "$SEED", "int", required=True, min=SEED_MIN, max=SEED_MAX,
                  description="Sampling seed; omitted → random."),
    WorkflowParam("width", "$WIDTH", "int", required=True, default=DEFAULT_IMAGE_WIDTH,
                  min=IMAGE_MIN_DIMENSION, max=IMAGE_MAX_DIMENSION,
                  description="Image width."),
    WorkflowParam("height", "$HEIGHT", "int", required=True, default=DEFAULT_IMAGE_HEIGHT,
                  min=IMAGE_MIN_DIMENSION, max=IMAGE_MAX_DIMENSION,
                  description="Image height."),
    # M1 参考图三槽位：reference_images[0..2] 依序注入 $REFERENCE_IMAGE_1..3；
    # 缺失/越界槽注入空字符串（provider 侧会裁掉未填充的 LoadImage 节点，
    # 避免 ComfyUI 空文件名校验失败——见 providers/image/comfyui.py）。
    WorkflowParam("reference_image_1", "$REFERENCE_IMAGE_1", "str", default="",
                  description="Reference image slot 1 (primary)."),
    WorkflowParam("reference_image_2", "$REFERENCE_IMAGE_2", "str", default="",
                  description="Reference image slot 2."),
    WorkflowParam("reference_image_3", "$REFERENCE_IMAGE_3", "str", default="",
                  description="Reference image slot 3."),
    # 旧单槽 token = 槽 1 别名（向后兼容：既有模板/测试可继续用 $REFERENCE_IMAGE）。
    WorkflowParam("reference_images", "$REFERENCE_IMAGE", "list[str]", default="",
                  description="Legacy single-slot alias of $REFERENCE_IMAGE_1 (first reference wins)."),
    # checkpoint 由 image.json 运行时配置解析（providers/image/comfyui.py 注入），
    # 业务层（Generation/Shot Service）永远不感知具体模型名（红线 #5）。
    WorkflowParam("checkpoint", "$CHECKPOINT", "str", default=DEFAULT_CHECKPOINT,
                  description="Checkpoint filename; resolved from the image runtime config."),
)

# Video parameters are declared now but NOT instantiated in the MVP image path.
RESERVED_PARAMETERS: tuple[WorkflowParam, ...] = (
    WorkflowParam("duration", "$DURATION", "int", reserved=True,
                  description="Reserved: video duration (seconds). Not used in MVP image."),
    WorkflowParam("resolution", "$RESOLUTION", "str", reserved=True,
                  description="Reserved: video resolution token. Not used in MVP image."),
)

# Backward-compatible sets derived from the schema (kept for workflow_service / tests).
REQUIRED_PLACEHOLDERS: tuple[str, ...] = tuple(
    p.placeholder for p in IMAGE_PARAMETERS if p.required
)

# The default schema declares the active (image) params plus the reserved (video)
# params, so placeholders()/PLACEHOLDERS stay aligned. Only non-reserved params are
# ever injected in the image path (see WorkflowSchema._active).
DEFAULT_PARAMETERS: tuple[WorkflowParam, ...] = IMAGE_PARAMETERS + RESERVED_PARAMETERS


class WorkflowSchema:
    """Declarative contract + validation for one workflow's logical parameters."""

    def __init__(
        self,
        parameters: tuple[WorkflowParam, ...] = DEFAULT_PARAMETERS,
    ) -> None:
        self.parameters = parameters
        self._by_name = {p.name: p for p in parameters}
        self._placeholder = {p.placeholder: p for p in parameters}
        # only active (non-reserved) params are injected in the current media path
        self._active = tuple(p for p in parameters if not p.reserved)

    # --- schema facts ----------------------------------------------------------

    @property
    def param_names(self) -> list[str]:
        return [p.name for p in self.parameters]

    def placeholders(self) -> set[str]:
        """All placeholder tokens declared in the schema (active + reserved)."""
        return set(self._placeholder)

    def required_placeholders(self) -> tuple[str, ...]:
        return tuple(p.placeholder for p in self.parameters if p.required)

    def placeholder_for(self, name: str) -> str:
        param = self._by_name.get(name)
        if param is None:
            raise KeyError(name)
        return param.placeholder

    # --- template (preflight) validation --------------------------------------

    def validate_template(self, template: dict) -> None:
        """Fail preflight when the template declares an unknown placeholder token or
        drops one the schema requires."""
        input_values = [
            value
            for node in template.values()
            if isinstance(node, dict)
            for value in node.get("inputs", {}).values()
        ]
        tokens = {value for value in input_values if isinstance(value, str) and value.startswith("$")}

        declared = self.placeholders()
        unknown = sorted(tokens - declared)
        if unknown:
            raise ValidationError(
                "Workflow template uses placeholder tokens not declared in the logical-parameter schema.",
                {"unknown_tokens": unknown, "declared": sorted(declared)},
            )
        missing = [
            p.placeholder for p in self.parameters if p.required and p.placeholder not in tokens
        ]
        if missing:
            raise ValidationError(
                "Workflow template is missing required placeholders.",
                {"missing": missing},
            )

    # --- request (build) validation + coercion ----------------------------------

    def coerce(
        self,
        *,
        prompt: str,
        negative_prompt: str | None = None,
        seed: int | None = None,
        width: int | None = None,
        height: int | None = None,
        reference_images: list[str] | None = None,
        checkpoint: str | None = None,
    ) -> dict[str, Any]:
        """Validate a request against the schema and return the {placeholder: value}
        injectable map (defaults applied, random seed resolved). Raises ValidationError
        (422) for type/range errors."""
        values: dict[str, Any] = {}
        refs = reference_images or []
        req: dict[str, Any] = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "seed": seed,
            "width": width,
            "height": height,
            "reference_image_1": refs[0] if refs else None,
            "reference_image_2": refs[1] if len(refs) > 1 else None,
            "reference_image_3": refs[2] if len(refs) > 2 else None,
            "reference_images": reference_images,
            "checkpoint": checkpoint,
        }
        for param in self._active:
            raw = req[param.name]
            value = self._validate_one(param, raw)
            values[param.placeholder] = value
        return values

    def _validate_one(self, param: WorkflowParam, raw: Any) -> Any:
        if param.value_type == "str":
            if raw is None:
                return param.default
            if not isinstance(raw, str):
                raise ValidationError(
                    f"Workflow parameter '{param.name}' must be a string.",
                    {"parameter": param.name, "placeholder": param.placeholder, "got": type(raw).__name__},
                )
            return raw if raw else param.default

        if param.value_type == "int":
            if raw is None:
                # seed has no static default → randomize at build time
                if param.name == "seed":
                    return random.randint(0, SEED_DEFAULT_RANGE)
                return param.default
            if isinstance(raw, bool) or not isinstance(raw, int):
                raise ValidationError(
                    f"Workflow parameter '{param.name}' must be an integer.",
                    {"parameter": param.name, "placeholder": param.placeholder, "got": type(raw).__name__},
                )
            if param.min is not None and raw < param.min:
                raise ValidationError(
                    f"Workflow parameter '{param.name}' is below the allowed minimum.",
                    {"parameter": param.name, "value": raw, "min": param.min},
                )
            if param.max is not None and raw > param.max:
                raise ValidationError(
                    f"Workflow parameter '{param.name}' exceeds the allowed maximum.",
                    {"parameter": param.name, "value": raw, "max": param.max},
                )
            return raw

        if param.value_type == "list[str]":
            if raw is None:
                return param.default
            if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
                raise ValidationError(
                    f"Workflow parameter '{param.name}' must be a list of strings.",
                    {"parameter": param.name, "placeholder": param.placeholder},
                )
            # legacy single-slot token: alias of slot 1 (first reference wins,
            # empty string when no reference — same value as $REFERENCE_IMAGE_1)
            return raw[0] if raw else param.default

        return param.default
