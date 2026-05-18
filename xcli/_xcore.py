"""
Shared helpers to boot xcore in standalone mode (no FastAPI/HTTP).
Used by CLI commands that need direct access to the plugin system.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from rich.console import Console

if TYPE_CHECKING:
    from xcore import Xcore

console = Console()

_CONFIG_CANDIDATES = [
    "integration.yaml", "integration.json",
    "config/integration.yaml", "config/integration.json",
]


def _require_config() -> Path:
    for c in _CONFIG_CANDIDATES:
        if Path(c).exists():
            return Path(c)
    console.print("[yellow]⚠[/yellow] No integration.yaml — run [cyan]xcli init[/cyan] first.")
    sys.exit(1)


def load_raw_config() -> dict:
    path = _require_config()
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


async def boot() -> "Xcore":
    """Boot xcore in standalone mode (no FastAPI). Reads integration.yaml automatically."""
    from xcore import Xcore
    _require_config()
    xcore = Xcore()
    await xcore.boot()
    return xcore


class _NullEvents:
    """Minimal event bus for sandbox subprocess without a full xcore boot."""
    def emit_sync(self, *a, **kw): pass
    async def emit(self, *a, **kw): pass
    def subscribe(self, *a, **kw): pass


class _NullCtx:
    """Minimal context for SandboxProcessManager without booting xcore."""
    _events = _NullEvents()
