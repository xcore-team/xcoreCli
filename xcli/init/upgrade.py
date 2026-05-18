"""
upgrade.py — Migrate an existing integration.yaml to the latest schema.

Strategy: deep-merge defaults → existing values win, missing keys are added.
The original file is backed up as integration.yaml.bak before writing.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from rich.console import Console
from rich.markup import escape
from rich.table import Table

console = Console()

# Full default schema — every key that xcli/xcore understands
_DEFAULTS: dict = {
    "app": {
        "name": "xcore-app",
        "env": "development",
        "debug": False,
        "secret_key": "change-me-in-production",
        "plugin_prefix": "/app",
        "plugin_tags": [],
        "server_key": "change-me-in-production",
        "server_key_iterations": 100000,
        "fastapi": {
            "title": "xcore-app",
            "version": "0.1.0",
            "docs_url": "/docs",
            "redoc_url": "/redoc",
            "openapi_url": "/openapi.json",
            "redirect_slashes": True,
        },
        "server": {
            "host": "0.0.0.0",
            "port": 8000,
            "workers": 1,
            "reload": True,
            "log_level": "DEBUG",
            "proxy_headers": True,
            "forwarded_allow_ips": "*",
        },
    },
    "plugins": {
        "directory": "./app",
        "secret_key": "change-me-in-production",
        "strict_trusted": False,
        "interval": 10,
        "entry_point": "src/main.py",
    },
    "services": {
        "databases": {
            "default": {
                "type": "sqlasync",
                "url": "sqlite+aiosqlite:///./xcore.db",
                "echo": False,
            }
        },
        "cache": {
            "backend": "memory",
            "ttl": 300,
            "max_size": 1000,
        },
        "scheduler": {
            "enabled": False,
            "backend": "memory",
            "timezone": "UTC",
        },
    },
    "observability": {
        "logging": {
            "level": "DEBUG",
            "format": "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            "file": "log/app.log",
            "max_bytes": 10485760,
            "backup_count": 5,
        },
        "metrics": {
            "enabled": False,
            "backend": "memory",
            "prefix": "xcore",
        },
        "tracing": {
            "enabled": False,
            "backend": "noop",
            "service_name": "xcore-app",
            "endpoint": None,
        },
    },
    "security": {
        "allowed_imports": [
            "fastapi", "json", "re", "math", "datetime", "typing",
            "dataclasses", "enum", "functools", "collections",
            "hashlib", "base64", "asyncio", "logging", "uuid",
        ],
        "forbidden_imports": [],
        "rate_limit_default": {
            "calls": 100,
            "period_seconds": 60,
        },
    },
    "marketplace": {
        "url": "https://marketplace.xcore.dev",
        "api_key": "",
        "timeout": 10,
        "cache_ttl": 300,
    },
}


def _deep_merge(defaults: dict, existing: dict) -> tuple[dict, list[str]]:
    """
    Returns (merged, added_keys) where:
    - existing values always win
    - missing keys from defaults are injected
    - added_keys lists the dotted paths of every key that was added
    """
    result = dict(existing)
    added: list[str] = []

    def _merge(base: dict, src: dict, target: dict, path: str) -> None:
        for key, default_val in base.items():
            full = f"{path}.{key}" if path else key
            if key not in src:
                target[key] = default_val
                added.append(full)
            elif isinstance(default_val, dict) and isinstance(src[key], dict):
                target[key] = dict(src[key])
                _merge(default_val, src[key], target[key], full)
            # else: existing value wins, already in target

    _merge(defaults, existing, result, "")
    return result, added


_CONFIG_CANDIDATES = [
    "integration.yaml", "integration.json",
    "config/integration.yaml", "config/integration.json",
]


def run_upgrade() -> None:
    # Find config file
    config_path: Path | None = None
    for c in _CONFIG_CANDIDATES:
        p = Path(c)
        if p.exists():
            config_path = p
            break

    if config_path is None:
        console.print("[yellow]⚠[/yellow] No integration.yaml found — run [cyan]xcli init[/cyan] first.")
        return

    console.print(f"\n[bold]xcli upgrade[/bold]  [dim]{config_path}[/dim]\n")

    existing = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    merged, added = _deep_merge(_DEFAULTS, existing)

    if not added:
        console.print("[green]✓[/green] Already up to date — no missing keys found.")
        return

    # Show what will be added
    table = Table(title=f"{len(added)} key(s) will be added")
    table.add_column("Key", style="cyan")
    table.add_column("Default value", style="dim")

    def _get_nested(d: dict, dotted: str):
        parts = dotted.split(".")
        for p in parts:
            if isinstance(d, dict):
                d = d.get(p)
            else:
                return None
        return d

    for key in added:
        val = _get_nested(_DEFAULTS, key)
        table.add_row(key, escape(str(val)))

    console.print(table)

    # Backup
    bak = config_path.with_suffix(".yaml.bak")
    bak.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
    console.print(f"\n[dim]Backup → {bak}[/dim]")

    # Write merged config
    config_path.write_text(
        yaml.dump(merged, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    console.print(f"[green]✓[/green] [cyan]{config_path}[/cyan] upgraded — {len(added)} key(s) added.")
