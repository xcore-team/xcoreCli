from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.tree import Tree

from xcli.config.runtime import load_raw_config, plugins_directory

console = Console()
name_re = re.compile(r'^[a-z][a-z0-9_]*$')

_DEFAULT_MARKETPLACE_API = 'https://marketplace.xcorehub.dev'


def marketplace_api_base() -> str:
    """Return the marketplace API base URL from integration.yaml, with fallback.

    `integration.yaml`'s `marketplace.url` is conventionally a bare domain
    (`marketplace.xcorehub.dev`, no scheme — see the backend's own
    integration.yaml) since it's also used to build the CORS allow-list.
    Used directly as an HTTP base URL that would produce a scheme-less,
    unusable URL for httpx — always ensure a scheme here rather than assume
    every caller of this config value remembers to add one.
    """
    try:
        cfg = load_raw_config(required=False)
        marketplace = cfg.get('marketplace', {})
        url = str(marketplace.get('api_url') or marketplace.get('url') or _DEFAULT_MARKETPLACE_API).rstrip('/')
    except Exception:
        url = _DEFAULT_MARKETPLACE_API
    if not url.startswith(('http://', 'https://')):
        url = f'https://{url}'
    return url


def marketplace_install_url(name: str, version: str) -> str:
    return f'{marketplace_api_base()}/app/marketplace/plugins/{name}/install?version={version}'


def plugins_dir() -> Path:
    return plugins_directory()


def registry_path() -> Path:
    """`.xcore-registry.json` — a sibling of every installed plugin
    directory, one entry per plugin name, recording how it got there
    (marketplace/git/zip + repository + pinned ref when known). Read by
    xcore-agent's packer at build time (see packer.builder._read_registry_
    source) as a fallback for a plugin with no explicit `source:` of its
    own in plugin.yaml — this is what lets `xcore-agent build` resolve a
    plugin from its real origin at deploy time automatically, instead of
    an operator hand-writing `source:` after every `xcli plugin install`."""
    return plugins_dir() / ".xcore-registry.json"


def record_install(name: str, entry: dict[str, Any]) -> None:
    """Add/replace this plugin's entry in the registry. Best-effort: a
    write failure here must never fail the install itself (the plugin is
    already on disk and usable — the registry only makes a later `xcore-
    agent build` smarter, it's not required for the plugin to work)."""
    path = registry_path()
    try:
        registry = json.loads(path.read_text()) if path.is_file() else {}
        if not isinstance(registry, dict):
            registry = {}
    except (OSError, ValueError):
        registry = {}
    registry[name] = {**entry, "installed_at": datetime.now(timezone.utc).isoformat()}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n")
    except OSError as exc:
        console.print(f"[dim yellow]Note: couldn't update {path.name}: {exc}[/dim yellow]")


def parse_x_repo(header_value: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Parse the marketplace install endpoint's `X-Repo: owner/repo@ref`
    response header into (repository_url, ref). Returns (None, None) if the
    header is absent or malformed — callers must treat that as 'unknown
    origin', never guess."""
    if not header_value or "@" not in header_value:
        return None, None
    repo_part, _, ref_part = header_value.rpartition("@")
    if not repo_part or not ref_part:
        return None, None
    return f"https://github.com/{repo_part}", ref_part


def print_tree(root: Path, created: list[Path]) -> None:
    tree = Tree(f'[bold green]{root.name}/[/bold green]')
    dirs: dict[str, Tree] = {}
    for path in sorted(created):
        rel = path.relative_to(root)
        parts = rel.parts
        current = tree
        for i, part in enumerate(parts[:-1]):
            key = '/'.join(parts[: i + 1])
            if key not in dirs:
                dirs[key] = current.add(f'[cyan]{part}/[/cyan]')
            current = dirs[key]
        current.add(f'[white]{parts[-1]}[/white]')
    console.print(tree)
