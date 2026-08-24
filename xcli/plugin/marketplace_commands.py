from __future__ import annotations

from typing import Any, Optional

import httpx
import typer
from typer import Typer

from xcli._credentials import get_api_key

from .shared import console, marketplace_api_base

# Contrat réel du backend (app/marketplace/src/routes/plugins.py) — pas le
# client générique xcore.marketplace.MarketplaceClient, dont le contrat
# suppose des routes (/plugins/trending, /plugins/search, /plugins/{name}/
# versions) qui n'existent pas côté serveur : recherche et tri sont des
# query params sur GET /plugins, pas des sous-routes ; les versions sont
# imbriquées dans la réponse de GET /plugins/{slug}, pas un endpoint séparé.
_LIST_PATH = '/app/marketplace/plugins'


def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    url = f'{marketplace_api_base()}{path}'
    try:
        resp = httpx.get(url, params=params, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        console.print(f'[red]HTTP {exc.response.status_code}:[/red] {url}')
        raise typer.Exit(1)
    except httpx.RequestError as exc:
        console.print(f'[red]Network error:[/red] {exc}')
        raise typer.Exit(1)


def _table(plugins: list[dict[str, Any]], title: str) -> None:
    from rich.table import Table

    table = Table(title=title)
    table.add_column('Name', style='cyan')
    table.add_column('Slug', style='dim')
    table.add_column('Latest', style='magenta')
    table.add_column('Rating', justify='right')
    table.add_column('Downloads', justify='right')
    table.add_column('Description')
    for plugin in plugins:
        rating = plugin.get('avg_rating') or 0
        table.add_row(
            str(plugin.get('name', '?')),
            str(plugin.get('slug', '?')),
            str(plugin.get('latest_version') or '—'),
            f"{rating:.1f}" if rating else '—',
            str(plugin.get('download_count', 0)),
            str(plugin.get('description') or ''),
        )
    console.print(table)


def register(app: Typer) -> None:
    @app.command('browse')
    def browse(
        sort: str = typer.Option('newest', '--sort', help='newest | downloads | rating'),
        limit: int = typer.Option(20, '--limit', min=1, max=200),
        category_id: Optional[str] = typer.Option(None, '--category', help='Filter by category id'),
    ) -> None:
        """List plugins published on the marketplace."""
        if sort not in ('newest', 'downloads', 'rating'):
            console.print(f"[red]Invalid --sort '{sort}'.[/red] Use: newest | downloads | rating")
            raise typer.Exit(1)
        with console.status('Fetching marketplace plugins...'):
            data = _get(_LIST_PATH, {'sort': sort, 'limit': limit, 'category_id': category_id})
        items = (data or {}).get('items', [])
        if not items:
            console.print('[yellow]No plugins found on marketplace.[/yellow]')
            return
        total = data.get('total', len(items))
        _table(items, f'Marketplace Plugins ({len(items)} of {total}, sort={sort})')

    @app.command('search')
    def search(
        query: str,
        limit: int = typer.Option(20, '--limit', min=1, max=200),
    ) -> None:
        """Search the marketplace by name or description."""
        with console.status(f"Searching for '[cyan]{query}[/cyan]'..."):
            data = _get(_LIST_PATH, {'search': query, 'limit': limit})
        items = (data or {}).get('items', [])
        if not items:
            console.print(f"[yellow]No results for '[cyan]{query}[/cyan]'.[/yellow]")
            return
        _table(items, f'Search results — {query}')

    @app.command('mine')
    def mine() -> None:
        """List YOUR plugins on the marketplace — public and private alike.

        `browse`/`search` above only ever see public plugins: they call
        GET /plugins unauthenticated, and the server only widens that to a
        caller's own private plugins for a JWT session — which `xcli` never
        holds (even after `xcli login`, which saves an API key + signing
        key via a device-code flow, never a browser session token). This
        command instead calls GET /plugins/mine with X-API-Key — the same
        auth `xcli plugin install` already uses successfully to fetch a
        private plugin you own, now also available for listing them.
        """
        api_key = get_api_key()
        if not api_key:
            console.print('[red]API key missing.[/red] Run: [cyan]xcli login[/cyan] or [cyan]xcli config set api-key xdk_...[/cyan]')
            raise typer.Exit(1)

        url = f'{marketplace_api_base()}{_LIST_PATH}/mine'
        with console.status('Fetching your plugins...'):
            try:
                resp = httpx.get(url, headers={'X-API-Key': api_key}, timeout=15, follow_redirects=True)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401:
                    console.print('[red]Invalid or revoked API key.[/red] Run: [cyan]xcli login[/cyan]')
                else:
                    console.print(f'[red]HTTP {exc.response.status_code}:[/red] {exc.response.text[:200]}')
                raise typer.Exit(1)
            except httpx.RequestError as exc:
                console.print(f'[red]Network error:[/red] {exc}')
                raise typer.Exit(1)

        items = resp.json() or []
        if not items:
            console.print('[yellow]No plugins yet.[/yellow] Publish one: [dim]xcli plugin marketplace info <slug>[/dim]')
            return
        _table(items, f'Your Plugins ({len(items)})')

    @app.command('info')
    def info(slug: str) -> None:
        """Show full details for a marketplace plugin before installing."""
        from rich.markup import escape
        from rich.panel import Panel

        with console.status(f'Fetching [cyan]{slug}[/cyan]...'):
            data = _get(f'{_LIST_PATH}/{slug}')
        if not data:
            console.print(f"[red]Plugin '[cyan]{slug}[/cyan]' not found on marketplace.[/red]")
            raise typer.Exit(1)

        versions = data.get('versions') or []
        lines = [
            f'[cyan]description:[/] {escape(str(data.get("description") or "—"))}',
            f'[cyan]latest_version:[/] {escape(str(data.get("latest_version") or "—"))}',
            f'[cyan]rating:[/] {data.get("avg_rating", 0):.1f} ({data.get("rating_count", 0)} ratings)',
            f'[cyan]downloads:[/] {data.get("download_count", 0)}',
            f'[cyan]visibility:[/] {escape(str(data.get("visibility", "public")))}',
            f'[cyan]homepage:[/] {escape(str(data.get("homepage") or "—"))}',
            f'[cyan]repository:[/] {escape(str(data.get("repository") or "—"))}',
            f'[cyan]versions ({len(versions)}):[/] ' + ', '.join(v.get('version', '?') for v in versions[:10]),
        ]
        console.print(Panel('\n'.join(lines), title=f'[bold]{escape(slug)}[/]', border_style='cyan'))
        console.print(f'\n[dim]Install: xcli plugin install {slug}[/dim]')
