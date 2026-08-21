from __future__ import annotations

import re
from pathlib import Path

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
