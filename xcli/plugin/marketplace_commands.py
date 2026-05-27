from __future__ import annotations

import asyncio
from typing import Any

import typer
from typer import Typer

from .shared import console


def _client():
    from xcore.configurations.loader import ConfigLoader
    from xcore.marketplace import MarketplaceClient

    return MarketplaceClient(ConfigLoader.load(None))


def _normalize_plugins(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        for key in ('items', 'plugins', 'results', 'data'):
            value = payload.get(key)
            if isinstance(value, list):
                items = value
                break
        else:
            items = [payload]
    else:
        items = [payload]

    normalized: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            normalized.append(item)
        else:
            normalized.append({'name': str(item), 'version': '?', 'author': '—', 'description': ''})
    return normalized


def _table(plugins: list[dict[str, Any]], title: str) -> None:
    from rich.table import Table

    table = Table(title=title)
    table.add_column('Name', style='cyan')
    table.add_column('Version', style='magenta')
    table.add_column('Author', style='dim')
    table.add_column('Description')
    for plugin in plugins:
        table.add_row(
            str(plugin.get('name') or plugin.get('slug', '?')),
            str(plugin.get('version', '?')),
            str(plugin.get('author', '—')),
            str(plugin.get('description', '')),
        )
    console.print(table)


def register(app: Typer) -> None:
    @app.command('browse')
    def browse() -> None:
        """List all plugins available on the marketplace."""
        with console.status('Fetching marketplace plugins...'):
            plugins = _normalize_plugins(asyncio.run(_client().list_plugins()))
        if not plugins:
            console.print('[yellow]No plugins found on marketplace.[/yellow]')
            return
        _table(plugins, f'Marketplace Plugins ({len(plugins)})')

    @app.command('trending')
    def trending() -> None:
        """Show trending plugins on the marketplace."""
        with console.status('Fetching trending plugins...'):
            plugins = _normalize_plugins(asyncio.run(_client().trending()))
        if not plugins:
            console.print('[yellow]No trending plugins.[/yellow]')
            return
        _table(plugins, 'Trending Plugins')

    @app.command('search')
    def search(query: str) -> None:
        """Search the marketplace for plugins by keyword or tag."""
        with console.status(f"Searching for '[cyan]{query}[/cyan]'..."):
            results = _normalize_plugins(asyncio.run(_client().search(query)))
        if not results:
            console.print(f"[yellow]No results for '[cyan]{query}[/cyan]'.[/yellow]")
            return
        _table(results, f'Search results — {query}')

    @app.command('info')
    def info(name: str) -> None:
        """Show full details for a marketplace plugin before installing."""
        from rich.markup import escape
        from rich.panel import Panel

        with console.status(f'Fetching [cyan]{name}[/cyan]...'):
            data = asyncio.run(_client().get_plugin(name))
        if not data:
            console.print(f"[red]Plugin '[cyan]{name}[/cyan]' not found on marketplace.[/red]")
            raise typer.Exit(1)
        lines = [f'[cyan]{key}:[/] {escape(str(value))}' for key, value in data.items()]
        console.print(Panel('\n'.join(lines), title=f'[bold]{escape(name)}[/]', border_style='cyan'))

    @app.command('rate')
    def rate(name: str, score: int = typer.Option(..., min=1, max=5, help='Score 1–5')) -> None:
        """Rate a marketplace plugin (1–5 stars)."""
        asyncio.run(_client().rate_plugin(name, score=score))
        console.print(f'[green]✓[/green] Rated [cyan]{name}[/cyan] [magenta]{score}/5[/magenta].')
