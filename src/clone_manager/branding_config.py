"""Command-wise editable response and local branding asset defaults."""
from __future__ import annotations
import json
from .paths import APP_DATA_DIR

_REPO_ROOT = APP_DATA_DIR
_RESPONSE_FILE = _REPO_ROOT / "config" / "command_responses.json"
IMAGE_PATH = _REPO_ROOT / "assets" / "branding.jpg"
if not _RESPONSE_FILE.is_file():
    raise RuntimeError(f"Required command response config missing: {_RESPONSE_FILE}")
try:
    _CONFIG = json.loads(_RESPONSE_FILE.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    raise RuntimeError(f"Invalid command response config: {exc}") from exc
if not isinstance(_CONFIG, dict) or not isinstance(_CONFIG.get("commands"), dict):
    raise RuntimeError("command_responses.json must contain a commands object")
_BRANDING = _CONFIG.get("branding", {})
IMAGE_URL = str(_BRANDING.get("image_url", "")).strip()
FOOTER_MESSAGE = str(_BRANDING.get("footer_text", ""))
SMALL_CAPS = bool(_BRANDING.get("small_caps", True))
if not IMAGE_PATH.is_file():
    raise RuntimeError(f"Required local branding image is missing: {IMAGE_PATH}")
COMMAND_RESPONSES = _CONFIG["commands"]
