"""P4-T005 / P4-T006 — WorkflowSchema + Input Mapping formalisation tests.

Covers:
- Schema facts: placeholder mapping (logical name -> token), required placeholders,
  reserved (video) params declared but not instantiated in the image path.
- Template (preflight) validation: unknown placeholder token -> failure; missing
  required placeholder -> failure (retained REQUIRED_PLACEHOLDERS semantics).
- Build (request) validation: width/height out of 64..4096, illegal seed, wrong types
  -> ValidationError (422).
- Mapping injection compat: mapper.build still substitutes placeholders exactly as
  before (external signature unchanged), defaults (width/height/negative_prompt) and
  random seed resolution remain identical.
"""

import json

import pytest

from app.core.errors import ComfyUIError, ValidationError
from app.providers.comfyui.workflow_mapper import (
    DEFAULT_WORKFLOW_ID,
    PLACEHOLDERS,
    REQUIRED_PLACEHOLDERS,
    WorkflowMapper,
)
from app.providers.comfyui.workflow_schema import (
    IMAGE_PARAMETERS,
    RESERVED_PARAMETERS,
    WorkflowSchema,
)

_VALID_TEMPLATE = {
    "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "x.safetensors"}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "$PROMPT", "clip": ["3", 1]}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "$NEGATIVE_PROMPT", "clip": ["3", 1]}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": "$WIDTH", "height": "$HEIGHT", "batch_size": 1}},
    "12": {
        "class_type": "KSampler",
        "inputs": {"seed": "$SEED", "steps": 20, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["3", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]},
    },
    "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["3", 2]}},
    "14": {"class_type": "SaveImage", "inputs": {"filename_prefix": "studio/shot", "images": ["13", 0]}},
}


def _write_template(directory, filename: str, template: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(json.dumps(template), encoding="utf-8")


# --- schema facts -------------------------------------------------------------

def test_mapping_table_covers_known_placeholders() -> None:
    by_name = {p.name: p for p in IMAGE_PARAMETERS}
    assert by_name["prompt"].placeholder == "$PROMPT"
    assert by_name["negative_prompt"].placeholder == "$NEGATIVE_PROMPT"
    assert by_name["seed"].placeholder == "$SEED"
    assert by_name["width"].placeholder == "$WIDTH"
    assert by_name["height"].placeholder == "$HEIGHT"
    assert by_name["reference_images"].placeholder == "$REFERENCE_IMAGE"


def test_required_placeholders_semantics_preserved() -> None:
    assert REQUIRED_PLACEHOLDERS == ("$PROMPT", "$SEED", "$WIDTH", "$HEIGHT")
    schema = WorkflowSchema()
    assert schema.required_placeholders() == ("$PROMPT", "$SEED", "$WIDTH", "$HEIGHT")


def test_placeholders_constants_align_with_schema() -> None:
    schema = WorkflowSchema()
    # PLACEHOLDERS includes the reserved (video) tokens but not low-level node ids.
    assert {p for p in PLACEHOLDERS} == schema.placeholders()


def test_reserved_video_params_declared_not_active() -> None:
    reserved = {p.name for p in RESERVED_PARAMETERS}
    assert {"duration", "resolution"} <= reserved
    # reserved params must not appear in the image injection map
    active_names = {p.name for p in IMAGE_PARAMETERS}
    assert "duration" not in active_names
    assert "resolution" not in active_names


def test_schema_placeholder_for_and_bounds() -> None:
    schema = WorkflowSchema()
    assert schema.placeholder_for("width") == "$WIDTH"
    width = next(p for p in IMAGE_PARAMETERS if p.name == "width")
    assert width.min == 64 and width.max == 4096


# --- template (preflight) validation ------------------------------------------

def test_template_unknown_placeholder_fails(monkeypatch, tmp_path) -> None:
    template = json.loads(json.dumps(_VALID_TEMPLATE))
    template["12"]["inputs"]["cfg"] = 7.0  # keep node valid JSON shape
    # introduce a placeholder token NOT declared in the schema
    template["12"]["model"] = ["3", 0]
    template["99x"] = {"class_type": "KSampler", "inputs": {"seed": "$UNKNOWN_TOKEN", "steps": 1}}
    _write_template(tmp_path, "default_image_api.json", template)

    mapper = WorkflowMapper(DEFAULT_WORKFLOW_ID, workflows_dir=tmp_path)
    with pytest.raises(ComfyUIError, match="not declared"):
        mapper.preflight()


def test_template_missing_required_placeholder_fails(monkeypatch, tmp_path) -> None:
    template = json.loads(json.dumps(_VALID_TEMPLATE))
    del template["12"]["inputs"]["seed"]  # drop $SEED
    _write_template(tmp_path, "default_image_api.json", template)

    mapper = WorkflowMapper(DEFAULT_WORKFLOW_ID, workflows_dir=tmp_path)
    with pytest.raises(ComfyUIError, match="required placeholders"):
        mapper.preflight()


# --- build validation (422 / ValidationError) ---------------------------------

def test_build_rejects_width_out_of_range(tmp_path) -> None:
    _write_template(tmp_path, "default_image_api.json", _VALID_TEMPLATE)
    mapper = WorkflowMapper(DEFAULT_WORKFLOW_ID, workflows_dir=tmp_path)
    with pytest.raises(ValidationError):
        mapper.build(prompt="hi", width=8000, height=512)


def test_build_rejects_height_below_min(tmp_path) -> None:
    _write_template(tmp_path, "default_image_api.json", _VALID_TEMPLATE)
    mapper = WorkflowMapper(DEFAULT_WORKFLOW_ID, workflows_dir=tmp_path)
    with pytest.raises(ValidationError):
        mapper.build(prompt="hi", width=512, height=8)


def test_build_rejects_illegal_seed(tmp_path) -> None:
    _write_template(tmp_path, "default_image_api.json", _VALID_TEMPLATE)
    mapper = WorkflowMapper(DEFAULT_WORKFLOW_ID, workflows_dir=tmp_path)
    with pytest.raises(ValidationError):
        mapper.build(prompt="hi", seed=-5)


def test_build_rejects_non_int_dimension(tmp_path) -> None:
    _write_template(tmp_path, "default_image_api.json", _VALID_TEMPLATE)
    mapper = WorkflowMapper(DEFAULT_WORKFLOW_ID, workflows_dir=tmp_path)
    with pytest.raises(ValidationError):
        mapper.build(prompt="hi", width="512")


def test_schema_rejects_non_str_prompt() -> None:
    schema = WorkflowSchema()
    with pytest.raises(ValidationError):
        schema.coerce(prompt=123)


def test_schema_rejects_bad_reference_images_type() -> None:
    schema = WorkflowSchema()
    with pytest.raises(ValidationError):
        schema.coerce(prompt="x", reference_images=["ok", 42])


# --- mapping injection compat -------------------------------------------------

def test_build_injects_and_applies_defaults(tmp_path) -> None:
    _write_template(tmp_path, "default_image_api.json", _VALID_TEMPLATE)
    mapper = WorkflowMapper(DEFAULT_WORKFLOW_ID, workflows_dir=tmp_path)
    built = mapper.build(prompt="hello manga", seed=7, width=640, height=960)

    assert built["6"]["inputs"]["text"] == "hello manga"
    assert built["7"]["inputs"]["text"] == ""  # negative_prompt default
    assert built["12"]["inputs"]["seed"] == 7
    assert built["5"]["inputs"]["width"] == 640
    assert built["5"]["inputs"]["height"] == 960
    # untouched low-level fields preserved (Studio never sees node detail beyond placeholders)
    assert built["12"]["inputs"]["steps"] == 20


def test_build_resolves_random_seed_when_omitted(tmp_path) -> None:
    _write_template(tmp_path, "default_image_api.json", _VALID_TEMPLATE)
    mapper = WorkflowMapper(DEFAULT_WORKFLOW_ID, workflows_dir=tmp_path)
    built = mapper.build(prompt="x", width=128, height=128)
    seed = built["12"]["inputs"]["seed"]
    assert isinstance(seed, int) and 0 <= seed < 2**31


def test_build_defaults_width_height_when_omitted(tmp_path) -> None:
    _write_template(tmp_path, "default_image_api.json", _VALID_TEMPLATE)
    mapper = WorkflowMapper(DEFAULT_WORKFLOW_ID, workflows_dir=tmp_path)
    built = mapper.build(prompt="x")
    assert built["5"]["inputs"]["width"] == 512
    assert built["5"]["inputs"]["height"] == 912


def test_build_reference_images_uses_first(tmp_path) -> None:
    # keep $PROMPT present (required); park $REFERENCE_IMAGE in a non-required slot.
    template = json.loads(json.dumps(_VALID_TEMPLATE))
    template["5"]["inputs"]["guide"] = "$REFERENCE_IMAGE"
    _write_template(tmp_path, "default_image_api.json", template)

    mapper = WorkflowMapper(DEFAULT_WORKFLOW_ID, workflows_dir=tmp_path)
    built = mapper.build(prompt="x", reference_images=["/a.png", "/b.png"])
    # the reference placeholder resolved to the FIRST image when present
    assert built["5"]["inputs"]["guide"] == "/a.png"
