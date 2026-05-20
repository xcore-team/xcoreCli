from __future__ import annotations

import asyncio

import typer
import yaml
from rich.prompt import Confirm
from rich.table import Table
from typer import Typer

from .install_commands import _install_from_url
from .shared import console, plugins_dir




def _marketplace_client():
    from xcore.configurations.loader import ConfigLoader
    from xcore.marketplace import MarketplaceClient

    return MarketplaceClient(ConfigLoader.load(None))

def _installed_version(name: str) -> str | None:
    manifest_path = plugins_dir() / name / 'plugin.yaml'
    if not manifest_path.exists():
        return None
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding='utf-8')) or {}
        return str(raw.get('version', '?'))
    except Exception:
        return None


def _do_update(name: str, target_version: str | None) -> None:
    import shutil

    current = _installed_version(name)
    client = _marketplace_client()

    async def _resolve() -> tuple[str, str, str]:
        if target_version and target_version != 'latest':
            versions = await client.get_versions(name)
            match = next((item for item in versions if item.get('version') == target_version), None)
            if not match:
                console.print(f'[red]Version {target_version} not found for [cyan]{name}[/cyan].[/red]')
                raise typer.Exit(1)
            return match['download_url'], match.get('source_type', 'zip'), match['version']

        data = await client.get_plugin(name)
        if not data:
            console.print(f'[red]Plugin [cyan]{name}[/cyan] not found on marketplace.[/red]')
            raise typer.Exit(1)
        return data.get('download_url'), data.get('source_type', 'zip'), data.get('version', 'latest')

    url, source_type, resolved_version = asyncio.run(_resolve())
    if current == resolved_version:
        console.print(f'[green]{name} already at {resolved_version}.[/green]')
        return

    plugin_path = plugins_dir() / name
    if plugin_path.exists():
        shutil.rmtree(plugin_path)
    _install_from_url(name, url, source_type)
    console.print(f'[green]✓[/green] Updated [cyan]{name}[/cyan] to [magenta]{resolved_version}[/magenta].')


def register(app: Typer) -> None:
    @app.command('update')
    def update(name: str, version: str = typer.Argument('latest')) -> None:
        """Update a single plugin from the marketplace."""
        _do_update(name, version)

    @app.command('update-all')
    def update_all(check: bool = typer.Option(False, '--check', help='Only check for available updates.')) -> None:
        """Check for and apply updates for all installed plugins."""
        names = sorted(item.name for item in plugins_dir().iterdir() if item.is_dir() and not item.name.startswith('_'))
        if not names:
            console.print('[yellow]No installed plugins found.[/yellow]')
            return

        client = _marketplace_client()

        async def _fetch_all() -> list[tuple[str, str | None, str | None, str | None, str | None]]:
            results = []
            for plugin_name in names:
                current = _installed_version(plugin_name)
                try:
                    data = await client.get_plugin(plugin_name)
                    latest = data.get('version', '?') if data else None
                    url = data.get('download_url') if data else None
                    src = data.get('source_type', 'zip') if data else None
                except Exception:
                    latest = url = src = None
                results.append((plugin_name, current, latest, url, src))
            return results

        with console.status('Checking marketplace for updates...'):
            results = asyncio.run(_fetch_all())

        table = Table(title='Plugin Update Status')
        table.add_column('Plugin', style='cyan')
        table.add_column('Installed', style='dim')
        table.add_column('Latest', style='magenta')
        table.add_column('Status', justify='center')

        upgradable: list[tuple[str, str | None, str | None, str | None, str | None]] = []
        for plugin_name, current, latest, url, src in results:
            if latest is None:
                status = '[dim]not on marketplace[/dim]'
            elif current == latest:
                status = '[green]up to date[/green]'
            else:
                status = '[yellow]update available[/yellow]'
                upgradable.append((plugin_name, current, latest, url, src))
            table.add_row(plugin_name, current or '?', latest or '—', status)

        console.print(table)
        if not upgradable:
            console.print('\n[green]All plugins are up to date.[/green]')
            return
        if check:
            console.print(f'\n[yellow]{len(upgradable)} update(s) available.[/yellow] Run without [dim]--check[/dim] to apply.')
            return
        names_str = ', '.join(f'[cyan]{plugin_name}[/cyan]' for plugin_name, *_ in upgradable)
        if not Confirm.ask(f'\nUpdate {names_str}?', default=True):
            return

        for plugin_name, current, latest, url, src in upgradable:
            console.print(f'\nUpdating [cyan]{plugin_name}[/cyan]: [dim]{current}[/dim] → [magenta]{latest}[/magenta]')
            assert url is not None and src is not None
            _install_from_url(plugin_name, url, src)
            console.print(f'[green]✓[/green] {plugin_name} updated.')
