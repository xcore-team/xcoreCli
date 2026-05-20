"""
Shared helpers to boot xcore in standalone mode (no FastAPI/HTTP).
Used by CLI commands that need direct access to the plugin system.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console

from xcli.config.runtime import find_config_path, load_raw_config as _load_raw_config

if TYPE_CHECKING:
    from pathlib import Path
    from xcore import Xcore

console = Console()


def _require_config() -> 'Path':
    path = find_config_path(required=True)
    assert path is not None
    return path


def load_raw_config() -> dict:
    return _load_raw_config(required=True)


async def boot() -> 'Xcore':
    """Boot xcore in standalone mode (no FastAPI). Reads integration.yaml automatically."""
    from xcore import Xcore

    _require_config()
    xcore = Xcore()
    await xcore.boot()
    return xcore


class _NullEvents:
    """Minimal event bus for sandbox subprocess without a full xcore boot."""

    def emit_sync(self, *a, **kw):
        pass

    async def emit(self, *a, **kw):
        pass

    def subscribe(self, *a, **kw):
        pass


class _NullCtx:
    """Minimal context for SandboxProcessManager without booting xcore."""

    _events = _NullEvents()
