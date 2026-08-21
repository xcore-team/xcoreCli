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


def marketplace_services_directory(start: Path | None = None, default: str = './services') -> Path:
    """Where `xcli service install` extracts marketplace service extensions.

    Deliberately its own top-level key (`marketplace_services:`), not nested
    under the existing `services:` block — that key already means xcore's
    OWN internal ServiceContainer config (databases/cache/celery, see
    database_url() below), unrelated to the marketplace catalog. Reusing it
    here would silently collide with that existing, unrelated meaning."""
    cfg = load_raw_config(start=start, required=True)
    raw = cfg.get('marketplace_services', {}).get('directory', default)
    return resolve_config_path(raw, start)


def observability_log_file(start: Path | None = None, default: str = 'log/app.log') -> Path:
    cfg = load_raw_config(start=start, required=True)
    raw = cfg.get('observability', {}).get('logging', {}).get('file', default)
    return resolve_config_path(raw, start)


def _load_project_dotenv(cfg: dict, start: Path | None = None) -> None:
    """Same reasoning as xcli/migrations/runtime.py's own helper — reads the
    SAME `app.dotenv` key the running app uses (e.g. `conf/.env`), so
    ${VAR}-style placeholders resolve the same way they would at runtime."""
    dotenv_file = cfg.get('app', {}).get('dotenv')
    if not dotenv_file:
        return
    path = Path(dotenv_file)
    if not path.is_absolute():
        path = project_root(start) / path
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=path, override=False)
    except ImportError:
        console.print(f"[yellow]⚠[/yellow] python-dotenv not installed — [dim]{path}[/dim] not loaded.")


def database_url(start: Path | None = None) -> str:
    cfg = load_raw_config(start=start, required=True)
    _load_project_dotenv(cfg, start)

    databases = cfg.get('services', {}).get('databases', {})
    if not databases:
        console.print('[red]No services.databases.* found in integration.yaml[/red]')
        raise SystemExit(1)

    # `default` is the key `xcli init` scaffolds — a hand-built project may
    # name its only database something else (e.g. `db`); unambiguous in that
    # single-entry case, only a real error with more than one candidate.
    entry = databases.get('default')
    if entry is None:
        if len(databases) == 1:
            entry = next(iter(databases.values()))
        else:
            keys = ', '.join(databases.keys())
            console.print(
                f'[red]No services.databases.default entry, and multiple databases '
                f'configured ({keys}) — ambiguous which one to use.[/red]'
            )
            raise SystemExit(1)

    url = entry.get('url')
    if not url:
        console.print('[red]No "url" on the resolved database entry in integration.yaml[/red]')
        raise SystemExit(1)

    expanded = os.path.expandvars(str(url))
    if '$' in expanded:
        dotenv_hint = cfg.get('app', {}).get('dotenv')
        where = f'app.dotenv ({dotenv_hint})' if dotenv_hint else 'that the env var is set'
        console.print(f'[yellow]⚠[/yellow] Database URL still contains an unresolved variable — check {where}.')
    return expanded
