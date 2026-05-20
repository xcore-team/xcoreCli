from __future__ import annotations

import json

import typer
from typer import Typer

from xcli._run import run

from .shared import console


def register(app: Typer) -> None:
    @app.command('load')
    def load(name: str) -> None:
        """Load a plugin directly (boots xcore standalone)."""

        async def _run() -> None:
            from xcli._xcore import boot

            xcore = await boot()
            try:
                await xcore.plugins.load(name)
                console.print(f'[green]✓[/green] Plugin [cyan]{name}[/cyan] loaded.')
            finally:
                await xcore.plugins.shutdown()

        run(_run())

    @app.command('reload')
    def reload(name: str) -> None:
        """Reload a plugin directly (boots xcore standalone)."""

        async def _run() -> None:
            from xcli._xcore import boot

            xcore = await boot()
            try:
                await xcore.plugins.reload(name)
                console.print(f'[green]✓[/green] Plugin [cyan]{name}[/cyan] reloaded.')
            finally:
                await xcore.plugins.shutdown()

        run(_run())

    @app.command('unload')
    def unload(name: str) -> None:
        """Unload a plugin directly (boots xcore standalone)."""

        async def _run() -> None:
            from xcli._xcore import boot

            xcore = await boot()
            try:
                await xcore.plugins.unload(name)
                console.print(f'[green]✓[/green] Plugin [cyan]{name}[/cyan] unloaded.')
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
        """Call a plugin action directly (boots xcore standalone)."""

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
