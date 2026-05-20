from __future__ import annotations

import sys

import typer
import yaml
from rich.prompt import Confirm, Prompt
from typer import Typer

from .scaffold import scaffold
from .shared import console, name_re, plugins_dir, print_tree


def register(app: Typer) -> None:
    @app.command('new')
    def new() -> None:
        """Scaffold a new plugin in the directory from integration.yaml."""
        console.print('\n[bold]xcli plugin new[/bold]\n')
        plugins_root = plugins_dir()

        while True:
            name = Prompt.ask('Plugin name  [dim](lowercase, underscores)[/dim]')
            if name_re.match(name):
                break
            console.print('[red]Lowercase letters, digits and underscores only.[/red]')

        mode = Prompt.ask('Execution mode', choices=['trusted', 'sandboxed', 'legacy'], default='trusted')
        target = plugins_root / name

        if target.exists() and not Confirm.ask(f'[yellow]{target}[/yellow] exists. Continue?', default=False):
            sys.exit(0)

        created = scaffold({'name': name, 'execution_mode': mode}, target)
        console.print()
        print_tree(target, created)
        console.print(f'\n[green]✓[/green] [cyan]{target}[/cyan] ready.')

    @app.command('list')
    def list_plugins() -> None:
        """List installed plugins."""
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
        table.add_column('Entry', style='dim')

        for name in plugins:
            manifest_path = plugin_dir / name / 'plugin.yaml'
            version = mode = entry = '?'
            if manifest_path.exists():
                try:
                    raw = yaml.safe_load(manifest_path.read_text(encoding='utf-8')) or {}
                    version = str(raw.get('version', '?'))
                    mode = str(raw.get('execution_mode', '?'))
                    entry = str(raw.get('entry_point', raw.get('main', '?')))
                except Exception:
                    pass
            table.add_row(name, version, mode, entry)

        console.print(table)

    @app.command('health')
    def health() -> None:
        """Health-check all installed plugins."""
        from rich.markup import escape
        from rich.table import Table
        from xcore.kernel.security.signature import is_signed
        from xcore.kernel.security.validation import ASTScanner, ManifestValidator

        plugin_dir = plugins_dir()
        plugins = sorted(d for d in plugin_dir.iterdir() if d.is_dir() and not d.name.startswith('_'))
        if not plugins:
            console.print('[yellow]No plugins found.[/yellow]')
            return

        table = Table(title='Plugin Health Check')
        table.add_column('Plugin', style='cyan', no_wrap=True)
        table.add_column('Mode', justify='center')
        table.add_column('Sig', justify='center')
        table.add_column('AST', justify='center')
        table.add_column('Manifest', justify='center')
        table.add_column('Status', style='dim')

        ok_count = err_count = 0
        with console.status('[green]Analyzing plugins...'):
            for entry in plugins:
                try:
                    manifest, _, _ = ManifestValidator().load_and_validate(entry)
                    signed = '✅' if is_signed(manifest) else '⚠️'
                    scanner = ASTScanner()
                    result = scanner.scan(entry, whitelist=manifest.allowed_imports)
                    ast_ok = '✅' if result.passed else '❌'
                    table.add_row(entry.name, manifest.execution_mode.value, signed, ast_ok, '✅', '[green]OK[/]')
                    ok_count += 1
                except Exception as e:
                    table.add_row(entry.name, '[red]?[/]', '[red]?[/]', '[red]?[/]', '❌', f'[red]{escape(str(e))}[/]')
                    err_count += 1

        console.print(table)
        console.print(f'\n[bold]Result: [green]{ok_count} OK[/], [red]{err_count} error(s)[/][/]')

    @app.command('remove')
    def remove(name: str) -> None:
        """Remove an installed plugin."""
        import shutil

        plugin_path = plugins_dir() / name
        if not plugin_path.exists():
            console.print(f"[red]Plugin '[cyan]{name}[/cyan]' not found.[/red]")
            raise typer.Exit(1)
        if not Confirm.ask(f"[bold red]⚠ Remove '[cyan]{name}[/cyan]'?[/]", default=False):
            console.print('Cancelled.')
            return
        shutil.rmtree(plugin_path)
        console.print(f'[green]✓[/green] Plugin [cyan]{name}[/cyan] removed.')

    @app.command('info')
    def info(name: str) -> None:
        """Show details of an installed plugin."""
        from rich.console import Group
        from rich.markup import escape
        from rich.panel import Panel
        from xcore.kernel.security.signature import is_signed
        from xcore.kernel.security.validation import ManifestValidator

        plugin_path = plugins_dir() / name
        if not plugin_path.exists():
            console.print(f"[red]Plugin '[cyan]{name}[/cyan]' not found.[/red]")
            raise typer.Exit(1)

        try:
            manifest, _, _ = ManifestValidator().load_and_validate(plugin_path)
        except Exception as e:
            console.print(f'[red]Invalid manifest:[/red] {escape(str(e))}')
            raise typer.Exit(1)

        lines = [
            f'[bold cyan]Author     :[/] [magenta]{escape(str(manifest.author))}[/]',
            f'[bold cyan]Description:[/] {escape(str(manifest.description))}',
            f'[bold cyan]Mode       :[/] [yellow]{escape(str(manifest.execution_mode.value))}[/]',
            f'[bold cyan]Framework  :[/] [green]{escape(str(manifest.framework_version))}[/]',
            f'[bold cyan]Entry point:[/] [blue]{escape(str(manifest.entry_point))}[/]',
            f"[bold cyan]Signed     :[/] {'✅ yes' if is_signed(manifest) else '⚠️  no'}",
        ]
        if getattr(manifest, 'requires', None):
            deps = ', '.join(d.name if hasattr(d, 'name') else str(d) for d in manifest.requires)
            lines.append(f'[bold cyan]Requires   :[/] {escape(deps)}')
        if getattr(manifest, 'allowed_imports', None):
            lines.append(f"[bold cyan]Imports OK :[/] [dim]{escape(', '.join(map(str, manifest.allowed_imports)))}[/]")

        resources = manifest.resources
        lines += [
            '\n[bold white]Resources:[/]',
            f'  [cyan]timeout    :[/] [magenta]{resources.timeout_seconds}s[/]',
            f'  [cyan]max_memory :[/] [magenta]{resources.max_memory_mb} MB[/]',
            f'  [cyan]max_disk   :[/] [magenta]{resources.max_disk_mb} MB[/]',
            f'  [cyan]rate_limit :[/] [magenta]{resources.rate_limit.calls} calls / {resources.rate_limit.period_seconds}s[/]',
        ]
        if getattr(manifest, 'permissions', None):
            lines.append(f'\n[bold white]Permissions ({len(manifest.permissions)}):[/]')
            for permission in manifest.permissions:
                symbol = '✅' if permission.get('effect', 'allow') == 'allow' else '❌'
                lines.append(
                    f"  {symbol} {escape(str(permission.get('resource', '*')))} → {escape(str(permission.get('actions', ['*'])))}"
                )

        console.print(
            Panel(
                Group(*lines),
                title=f'[bold green]🔌 {escape(manifest.name)} v{escape(manifest.version)}[/]',
                expand=False,
                border_style='cyan',
            )
        )
