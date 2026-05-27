from __future__ import annotations

import json

import typer
from typer import Typer

from xcli._run import run

from .shared import console, plugins_dir


def register(app: Typer) -> None:
    @app.command('load')
    def load(name: str) -> None:
        """Load a plugin into the running xcore instance."""
        async def _run() -> None:
            from xcli._xcore import boot
            xcore = await boot()
            try:
                await xcore.plugins.load(name)
                console.print(f'[green]✓[/green] Plugin [cyan]{name}[/cyan] loaded.')
            finally:
                await xcore.plugins.shutdown()

        run(_run())

    @app.command('unload')
    def unload(name: str) -> None:
        """Unload a plugin and free its resources."""
        async def _run() -> None:
            from xcli._xcore import boot
            xcore = await boot()
            try:
                await xcore.plugins.unload(name)
                console.print(f'[green]✓[/green] Plugin [cyan]{name}[/cyan] unloaded.')
            finally:
                await xcore.plugins.shutdown()

        run(_run())

    @app.command('reload')
    def reload(name: str) -> None:
        """Reload a plugin (applies code and config changes)."""
        async def _run() -> None:
            from xcli._xcore import boot
            xcore = await boot()
            try:
                await xcore.plugins.reload(name)
                console.print(f'[green]✓[/green] Plugin [cyan]{name}[/cyan] reloaded.')
            finally:
                await xcore.plugins.shutdown()

        run(_run())

    @app.command('reload-all')
    def reload_all() -> None:
        """Reload all active plugins at once."""
        async def _run() -> None:
            from xcli._xcore import boot
            xcore = await boot()
            try:
                plugin_dir = plugins_dir()
                names = sorted(
                    d.name for d in plugin_dir.iterdir()
                    if d.is_dir() and not d.name.startswith('_')
                )
                if not names:
                    console.print('[yellow]No plugins found.[/yellow]')
                    return
                ok_count = err_count = 0
                for pname in names:
                    try:
                        await xcore.plugins.reload(pname)
                        console.print(f'[green]✓[/green] {pname}')
                        ok_count += 1
                    except Exception as e:
                        from rich.markup import escape
                        console.print(f'[red]✗[/red] {pname}: {escape(str(e))}')
                        err_count += 1
                console.print(f'\n[bold]Result: [green]{ok_count} reloaded[/], [red]{err_count} error(s)[/][/]')
            finally:
                await xcore.plugins.shutdown()

        run(_run())

    @app.command('status')
    def status() -> None:
        """Show runtime status of all loaded plugins."""
        async def _run() -> None:
            from rich.table import Table
            from xcli._xcore import boot

            xcore = await boot()
            try:
                data = xcore.plugins.status()
                table = Table(title=f"Plugin Runtime Status ({data['count']} plugins)")
                table.add_column('Name', style='cyan')
                table.add_column('State', justify='center')
                table.add_column('Mode', style='green')
                for plugin in data['plugins']:
                    state = plugin.get('state', '?')
                    color = 'green' if state == 'running' else 'yellow'
                    table.add_row(plugin.get('name', '?'), f'[{color}]{state}[/]', plugin.get('mode', '?'))
                console.print(table)
            finally:
                await xcore.plugins.shutdown()

        run(_run())

    @app.command('call')
    def call(
        name: str,
        action: str,
        payload: str = typer.Option('{}', '--payload', '-p', help='JSON payload'),
    ) -> None:
        """Call a plugin action directly."""
        async def _run() -> None:
            from xcli._xcore import boot
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as e:
                console.print(f'[red]Invalid JSON payload:[/] {e}')
                raise typer.Exit(1)

            xcore = await boot()
            try:
                result = await xcore.plugins.call(name, action, data)
                console.print(result)
            finally:
                await xcore.plugins.shutdown()

        run(_run())
