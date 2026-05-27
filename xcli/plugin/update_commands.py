from __future__ import annotations

import asyncio
from typing import Optional

import typer
import yaml
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


def _fetch_latest(client, name: str) -> tuple[str | None, str | None, str | None]:
    """Returns (version, download_url, source_type) from marketplace."""
    async def _get():
        data = await client.get_plugin(name)
        if not data:
            return None, None, None
        return data.get('version'), data.get('download_url'), data.get('source_type', 'zip')

    return asyncio.run(_get())


def _do_update(name: str, target_version: str | None, dry_run: bool) -> None:
    import shutil

    current = _installed_version(name)
    client = _marketplace_client()

    async def _resolve() -> tuple[str | None, str | None, str]:
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
        console.print(f'[green]{name}[/green] already at [magenta]{resolved_version}[/magenta].')
        return

    console.print(f'  [cyan]{name}[/cyan]: [dim]{current}[/dim] → [magenta]{resolved_version}[/magenta]')
    if dry_run:
        return

    plugin_path = plugins_dir() / name
    if plugin_path.exists():
        shutil.rmtree(plugin_path)
    _install_from_url(name, url, source_type)
    console.print(f'[green]✓[/green] Updated [cyan]{name}[/cyan] to [magenta]{resolved_version}[/magenta].')


def register(app: Typer) -> None:

    @app.command('check')
    def check() -> None:
        """Check all installed plugins for available updates."""
        names = sorted(
            item.name for item in plugins_dir().iterdir()
            if item.is_dir() and not item.name.startswith('_')
        )
        if not names:
            console.print('[yellow]No installed plugins found.[/yellow]')
            return

        client = _marketplace_client()

        async def _fetch_all() -> list[tuple[str, str | None, str | None]]:
            results = []
            for pname in names:
                current = _installed_version(pname)
                try:
                    data = await client.get_plugin(pname)
                    latest = data.get('version', '?') if data else None
                except Exception:
                    latest = None
                results.append((pname, current, latest))
            return results

        with console.status('Checking marketplace for updates...'):
            results = asyncio.run(_fetch_all())

        table = Table(title='Plugin Update Status')
        table.add_column('Plugin', style='cyan')
        table.add_column('Installed', style='dim')
        table.add_column('Latest', style='magenta')
        table.add_column('Status', justify='center')

        update_count = 0
        for pname, current, latest in results:
            if latest is None:
                status = '[dim]not on marketplace[/dim]'
            elif current == latest:
                status = '[green]up to date[/green]'
            else:
                status = '[yellow]update available[/yellow]'
                update_count += 1
            table.add_row(pname, current or '?', latest or '—', status)

        console.print(table)
        if update_count:
            console.print(f'\n[yellow]{update_count} update(s) available.[/yellow] Run [cyan]xcli plugin update --all[/cyan] to apply.')
        else:
            console.print('\n[green]All plugins are up to date.[/green]')

    @app.command('apply')
    def apply(
        name: Optional[str] = typer.Argument(None, help='Plugin name to update (omit to use --all)'),
        all_plugins: bool = typer.Option(False, '--all', help='Update all installed plugins'),
        version: Optional[str] = typer.Option(None, '--version', help='Target a specific version'),
        dry_run: bool = typer.Option(False, '--dry-run', help='Show what would be updated without applying'),
    ) -> None:
        """Update one plugin or all plugins from the marketplace.

        Examples:
            xcli plugin update apply my-plugin
            xcli plugin update apply my-plugin --version 1.2.3
            xcli plugin update apply --all
            xcli plugin update apply --all --dry-run
        """
        if not name and not all_plugins:
            console.print('[red]Provide a plugin name or use --all.[/red]')
            raise typer.Exit(1)

        if dry_run:
            console.print('[dim]Dry run — no changes will be made.[/dim]\n')

        if all_plugins:
            names = sorted(
                item.name for item in plugins_dir().iterdir()
                if item.is_dir() and not item.name.startswith('_')
            )
            if not names:
                console.print('[yellow]No installed plugins found.[/yellow]')
                return
            for pname in names:
                _do_update(pname, version, dry_run)
        else:
            _do_update(name, version, dry_run)
