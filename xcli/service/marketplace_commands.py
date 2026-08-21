from __future__ import annotations

from typing import Any, Optional

import typer
from typer import Typer

# _get is a generic HTTP-GET-with-friendly-error helper — catalog-agnostic,
# imported rather than forked (one implementation to keep in sync).
from xcli.plugin.marketplace_commands import _get

from .shared import console

# Contrat réel du backend (app/xservices/src/routes/services.py) — GET
# /services renvoie une liste brute (pas de pagination items/total, contrairement
# à /marketplace/plugins), GET /services/{slug} renvoie le détail avec ses
# versions imbriquées. Miroir du module plugin, pas d'abstraction partagée :
# app/xservices/.../install.py dit lui-même "Miroir de app/marketplace/.../
# install.py" — même choix côté client.
_LIST_PATH = '/app/xservices/services'


def _table(services: list[dict[str, Any]], title: str) -> None:
    from rich.table import Table

    table = Table(title=title)
    table.add_column('Name', style='cyan')
    table.add_column('Slug', style='dim')
    table.add_column('Latest', style='magenta')
    table.add_column('Rating', justify='right')
    table.add_column('Installs', justify='right')
    table.add_column('Description')
    for svc in services:
        rating = svc.get('avg_rating') or 0
        table.add_row(
            str(svc.get('name', '?')),
            str(svc.get('slug', '?')),
            str(svc.get('latest_version') or '—'),
            f"{rating:.1f}" if rating else '—',
            str(svc.get('install_count', 0)),
            str(svc.get('description') or ''),
        )
    console.print(table)


def register(app: Typer) -> None:
    @app.command('browse')
    def browse(
        sort: str = typer.Option('newest', '--sort', help='newest | installs | rating'),
        limit: int = typer.Option(20, '--limit', min=1, max=200),
        category_id: Optional[str] = typer.Option(None, '--category', help='Filter by category id'),
    ) -> None:
        """List service extensions published on the marketplace."""
        if sort not in ('newest', 'installs', 'rating'):
            console.print(f"[red]Invalid --sort '{sort}'.[/red] Use: newest | installs | rating")
            raise typer.Exit(1)
        with console.status('Fetching marketplace service extensions...'):
            items = _get(_LIST_PATH, {'sort': sort, 'limit': limit, 'category_id': category_id}) or []
        if not items:
            console.print('[yellow]No service extensions found on marketplace.[/yellow]')
            return
        _table(items, f'Marketplace Service Extensions ({len(items)}, sort={sort})')

    @app.command('search')
    def search(
        query: str,
        limit: int = typer.Option(20, '--limit', min=1, max=200),
    ) -> None:
        """Search the marketplace service catalog by name or description."""
        with console.status(f"Searching for '[cyan]{query}[/cyan]'..."):
            items = _get(_LIST_PATH, {'search': query, 'limit': limit}) or []
        if not items:
            console.print(f"[yellow]No results for '[cyan]{query}[/cyan]'.[/yellow]")
            return
        _table(items, f'Search results — {query}')

    @app.command('info')
    def info(slug: str) -> None:
        """Show full details for a marketplace service extension before installing."""
        from rich.markup import escape
        from rich.panel import Panel

        with console.status(f'Fetching [cyan]{slug}[/cyan]...'):
            data = _get(f'{_LIST_PATH}/{slug}')
        if not data:
            console.print(f"[red]Service extension '[cyan]{slug}[/cyan]' not found on marketplace.[/red]")
            raise typer.Exit(1)

        versions = data.get('versions') or []
        lines = [
            f'[cyan]description:[/] {escape(str(data.get("description") or "—"))}',
            f'[cyan]latest_version:[/] {escape(str(data.get("latest_version") or "—"))}',
            f'[cyan]rating:[/] {data.get("avg_rating", 0):.1f} ({data.get("rating_count", 0)} ratings)',
            f'[cyan]installs:[/] {data.get("install_count", 0)}',
            f'[cyan]visibility:[/] {escape(str(data.get("visibility", "public")))}',
            f'[cyan]homepage:[/] {escape(str(data.get("homepage") or "—"))}',
            f'[cyan]repository:[/] {escape(str(data.get("repository") or "—"))}',
            f'[cyan]versions ({len(versions)}):[/] ' + ', '.join(v.get('version', '?') for v in versions[:10]),
        ]
        console.print(Panel('\n'.join(lines), title=f'[bold]{escape(slug)}[/]', border_style='cyan'))
        console.print(f'\n[dim]Install: xcli service install {slug}[/dim]')
