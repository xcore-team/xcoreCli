from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

console = Console()

CONFIG_ENV_VARS = ("XCORE_CONFIG", "XCLI_CONFIG")
CONFIG_CANDIDATES = (
    "integration.yaml",
    "integration.json",
    "config/integration.yaml",
    "config/integration.json",
)


def iter_config_candidates(start: Path | None = None) -> list[Path]:
    base = (start or Path.cwd()).resolve()
    candidates: list[Path] = []

    for env_name in CONFIG_ENV_VARS:
        raw = os.environ.get(env_name)
        if raw:
            candidates.append(Path(raw).expanduser())

    roots = [base, *base.parents]
    seen: set[Path] = set()
    for current_root in roots:
        for candidate in CONFIG_CANDIDATES:
            path = (current_root / candidate).resolve()
            if path not in seen:
                seen.add(path)
                candidates.append(path)
    return candidates


def find_config_path(start: Path | None = None, required: bool = True) -> Path | None:
    for path in iter_config_candidates(start):
        if path.exists():
            return path.resolve()
    if required:
        console.print("[yellow]⚠[/yellow] No integration.yaml — run [cyan]xcli init[/cyan] first.")
        raise SystemExit(1)
    return None


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding='utf-8'))
    return data if isinstance(data, dict) else {}


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    return data if isinstance(data, dict) else {}


def load_raw_config(start: Path | None = None, required: bool = True) -> dict[str, Any]:
    path = find_config_path(start=start, required=required)
    if path is None:
        return {}
    if path.suffix.lower() == '.json':
        return _load_json(path)
    return _load_yaml(path)


def project_root(start: Path | None = None) -> Path:
    path = find_config_path(start=start, required=True)
    assert path is not None
    return path.parent.resolve()


def resolve_config_path(raw_path: str | Path, start: Path | None = None) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()
    return (project_root(start) / path).resolve()


def plugins_directory(start: Path | None = None, default: str = './app') -> Path:
    cfg = load_raw_config(start=start, required=True)
    raw = cfg.get('plugins', {}).get('directory', default)
    return resolve_config_path(raw, start)


def observability_log_file(start: Path | None = None, default: str = 'log/app.log') -> Path:
    cfg = load_raw_config(start=start, required=True)
    raw = cfg.get('observability', {}).get('logging', {}).get('file', default)
    return resolve_config_path(raw, start)


def database_url(start: Path | None = None) -> str:
    cfg = load_raw_config(start=start, required=True)
    databases = cfg.get('services', {}).get('databases', {})
    default_db = databases.get('default', {})
    url = default_db.get('url')
    if not url:
        console.print('[red]No services.databases.default.url found in integration.yaml[/red]')
        raise SystemExit(1)
    return str(url)
