import json
import os
from pathlib import Path

_CONFIG_DIR = Path.home() / ".xcli"
_CONFIG_FILE = _CONFIG_DIR / "config.json"


def _load() -> dict:
    if _CONFIG_FILE.exists():
        try:
            return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_credential(key: str, value: str) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = _load()
    data[key] = value
    _CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _CONFIG_FILE.chmod(0o600)


def get_api_key() -> str | None:
    return os.environ.get("XCLI_API_KEY") or _load().get("api-key")


def get_signing_key() -> str | None:
    return os.environ.get("XCLI_SIGNING_KEY") or _load().get("signing-key")
