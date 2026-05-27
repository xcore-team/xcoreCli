from __future__ import annotations

import os
from pathlib import Path

import typer
import yaml
from typer import Typer

from .scaffold import scaffold
from .shared import console, name_re, plugins_dir, print_tree


def register(app: Typer) -> None:

    @app.command('scaffold')
    def scaffold_cmd(
        name: str = typer.Argument(..., help='Plugin name (lowercase, underscores)'),
        mode: str = typer.Option('trusted', '--mode', '-m', help='trusted | sandboxed | legacy'),
        description: str = typer.Option('', '--description', '-d', help='Plugin description'),
        author: str = typer.Option('', '--author', '-a', help='Author'),
        version: str = typer.Option('0.1.0', '--version', '-v', help='Initial version'),
        has_db: bool = typer.Option(False, '--db', help='Include models.py + schemas.py'),
        has_cache: bool = typer.Option(False, '--cache', help='Inject cache service'),
        has_scheduler: bool = typer.Option(False, '--scheduler', help='Inject scheduler service'),
        no_routes: bool = typer.Option(False, '--no-routes', help='Skip FastAPI router generation'),
        timeout: int = typer.Option(30, '--timeout', help='Timeout per call in seconds (sandboxed)'),
        memory: int = typer.Option(256, '--memory', help='Max memory in MB (sandboxed)'),
        disk: int = typer.Option(100, '--disk', help='Max disk in MB (sandboxed)'),
        force: bool = typer.Option(False, '--force', '-f', help='Overwrite if plugin already exists'),
    ) -> None:
        """Scaffold a new plugin in the plugins directory."""
        if not name_re.match(name):
            console.print('[red]Invalid name.[/red] Use lowercase letters, digits and underscores only.')
            raise typer.Exit(1)

        if mode not in ('trusted', 'sandboxed', 'legacy'):
            console.print(f'[red]Invalid mode:[/red] {mode}. Valid values: trusted, sandboxed, legacy')
            raise typer.Exit(1)

        plugins_root = plugins_dir()
        target = plugins_root / name

        if target.exists() and not force:
            console.print(f'[yellow]{target}[/yellow] already exists. Use [cyan]--force[/cyan] to overwrite.')
            raise typer.Exit(1)

        cfg = {
            'name':            name,
            'description':     description or f'Plugin {name}',
            'author':          author,
            'version':         version,
            'execution_mode':  mode,
            'has_db':          has_db,
            'has_cache':       has_cache,
            'has_scheduler':   has_scheduler,
            'has_routes':      not no_routes,
            'timeout_seconds': timeout,
            'max_memory_mb':   memory,
            'max_disk_mb':     disk,
        }

        created = scaffold(cfg, target)
        console.print()
        print_tree(target, created)
        console.print(f'\n[green]✓[/green] Plugin [cyan]{name}[/cyan] → [dim]{target}[/dim]')
        if mode == 'sandboxed':
            console.print(f'  [cyan]xcli sandbox run {name}[/cyan]')
        else:
            console.print(f'  [cyan]xcli plugin runtime load {name}[/cyan]')

    @app.command('link')
    def link(
        path: str = typer.Option(..., '--path', '-p', help='Path to plugin source directory'),
        name: str = typer.Option('', '--name', '-n', help='Override plugin name (default: source directory name)'),
    ) -> None:
        """Create a symlink from plugins directory to a local development source."""
        source = Path(path).resolve()
        if not source.exists() or not source.is_dir():
            console.print(f'[red]Source not found or not a directory:[/red] {source}')
            raise typer.Exit(1)

        plugin_name = name or source.name
        if not name_re.match(plugin_name):
            console.print(f'[red]Invalid plugin name:[/red] {plugin_name}. Use lowercase letters, digits and underscores.')
            raise typer.Exit(1)

        dest = plugins_dir() / plugin_name
        if dest.exists() or dest.is_symlink():
            console.print(f'[yellow]{dest}[/yellow] already exists. Remove it first with [cyan]xcli plugin local unlink {plugin_name}[/cyan].')
            raise typer.Exit(1)

        dest.symlink_to(source)
        console.print(f'[green]✓[/green] Linked [cyan]{plugin_name}[/cyan]: [dim]{dest}[/dim] → [dim]{source}[/dim]')
        console.print(f'  [dim]Changes in {source} are reflected immediately.[/dim]')

    @app.command('unlink')
    def unlink(name: str = typer.Argument(..., help='Plugin name to unlink')) -> None:
        """Remove a symlink created by `xcli plugin local link`."""
        dest = plugins_dir() / name
        if not dest.is_symlink():
            if dest.exists():
                console.print(f'[red]{name}[/red] is not a symlink — use [cyan]xcli plugin remove {name}[/cyan] to remove installed plugins.')
            else:
                console.print(f"[red]Plugin '{name}' not found.[/red]")
            raise typer.Exit(1)

        real = dest.resolve()
        dest.unlink()
        console.print(f'[green]✓[/green] Unlinked [cyan]{name}[/cyan] (source: [dim]{real}[/dim])')

    @app.command('list')
    def list_plugins() -> None:
        """List installed plugins (including symlinked ones)."""
        from rich.table import Table

        plugin_dir = plugins_dir()
        if not plugin_dir.exists():
            console.print(f'[yellow]Plugin directory not found:[/yellow] {plugin_dir}')
            return

        plugins = sorted(d.name for d in plugin_dir.iterdir() if d.is_dir() and not d.name.startswith('_'))
        if not plugins:
            console.print('[yellow]No plugins installed.[/yellow]')
            return

        table = Table(title=f'Installed Plugins ({len(plugins)})')
        table.add_column('Name', style='cyan', no_wrap=True)
        table.add_column('Version', style='magenta')
        table.add_column('Mode', style='green')
        table.add_column('Type', style='dim')
        table.add_column('Entry', style='dim')

        for pname in plugins:
            plugin_path = plugin_dir / pname
            link_type = '[cyan]symlink[/cyan]' if plugin_path.is_symlink() else 'installed'
            manifest_path = plugin_path / 'plugin.yaml'
            version = mode = entry = '?'
            if manifest_path.exists():
                try:
                    raw = yaml.safe_load(manifest_path.read_text(encoding='utf-8')) or {}
                    version = str(raw.get('version', '?'))
                    mode = str(raw.get('execution_mode', '?'))
                    entry = str(raw.get('entry_point', raw.get('main', '?')))
                except Exception:
                    pass
            table.add_row(pname, version, mode, link_type, entry)

        console.print(table)
