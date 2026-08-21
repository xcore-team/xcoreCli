from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.table import Table
from typer import Typer

from .install_commands import _marketplace_install
from .marketplace_commands import _LIST_PATH, _get
from .shared import console, plugins_dir


def _installed_version(name: str) -> str | None:
    manifest_path = plugins_dir() / name / 'plugin.yaml'
    if not manifest_path.exists():
        return None
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding='utf-8')) or {}
        return str(raw.get('version', '?'))
    except Exception:
        return None


def _resolve_version(name: str, target_version: str | None) -> str:
    """Resolve 'latest'/omitted to the actual latest version, or confirm a
    specific --version exists — both read from GET /plugins/{slug} (see
    marketplace_commands._get), the same public endpoint browse/search/info
    use. There is no separate download_url returned anywhere: the real
    download always goes through the signed /install endpoint, handled by
    _marketplace_install (install_commands.py) — never duplicated here."""
    data = _get(f'{_LIST_PATH}/{name}')
    if not data:
        console.print(f'[red]Plugin [cyan]{name}[/cyan] not found on marketplace.[/red]')
        raise typer.Exit(1)

    if target_version and target_version != 'latest':
        versions = {v.get('version') for v in (data.get('versions') or [])}
        if target_version not in versions:
            console.print(f'[red]Version {target_version} not found for [cyan]{name}[/cyan].[/red]')
            raise typer.Exit(1)
        return target_version

    latest = data.get('latest_version')
    if not latest:
        console.print(f'[red]No published version found for [cyan]{name}[/cyan].[/red]')
        raise typer.Exit(1)
    return latest


def _do_update(name: str, target_version: str | None, dry_run: bool) -> None:
    import shutil
    import tempfile

    current = _installed_version(name)
    resolved_version = _resolve_version(name, target_version)

    if current == resolved_version:
        console.print(f'[green]{name}[/green] already at [magenta]{resolved_version}[/magenta].')
        return

    console.print(f'  [cyan]{name}[/cyan]: [dim]{current}[/dim] → [magenta]{resolved_version}[/magenta]')
    if dry_run:
        return

    plugin_path = plugins_dir() / name
    backup_dir: Path | None = None
    if plugin_path.exists():
        backup_dir = Path(tempfile.mkdtemp(prefix=f"{name}_backup_"))
        shutil.copytree(plugin_path, backup_dir / name)
        # _marketplace_install clears plugin_path itself before extracting —
        # no rmtree needed here, just keep the backup around until it succeeds.
    try:
        _marketplace_install(name, resolved_version)
    except Exception as exc:
        if backup_dir is not None and backup_dir.exists():
            shutil.rmtree(plugin_path, ignore_errors=True)
            shutil.copytree(backup_dir / name, plugin_path)
            console.print(f'[yellow]⚠[/yellow] Restored [cyan]{name}[/cyan] from backup.')
        if backup_dir is not None:
            shutil.rmtree(backup_dir, ignore_errors=True)
        console.print(f'[red]✗[/red] Update failed: {exc}')
        raise typer.Exit(1) from exc
    if backup_dir is not None:
        shutil.rmtree(backup_dir, ignore_errors=True)
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

        def _fetch_all() -> list[tuple[str, str | None, str | None]]:
            results = []
            for pname in names:
                current = _installed_version(pname)
                try:
                    data = _get(f'{_LIST_PATH}/{pname}')
                    latest = data.get('latest_version') if data else None
                except Exception:
                    latest = None
                results.append((pname, current, latest))
            return results

        with console.status('Checking marketplace for updates...'):
            results = _fetch_all()

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
            console.print(f'\n[yellow]{update_count} update(s) available.[/yellow] Run [cyan]xcli plugin update apply --all[/cyan] to apply.')
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
