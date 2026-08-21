from __future__ import annotations

from typing import Optional

import httpx
import typer
from typer import Typer

from xcli._credentials import get_api_key, get_signing_key

# Pure, catalog-agnostic, security-sensitive — one implementation to keep in
# sync, not forked (see xcli/plugin/install_commands.py for the definition).
from xcli.plugin.install_commands import _verify_signature

from .shared import console, service_install_url, services_dir


def _server_detail(resp: httpx.Response) -> str | None:
    """Same reasoning as xcli/plugin/install_commands.py's own helper — the
    server's `{"detail": "..."}` is specific and actionable, a single
    hardcoded guess per status code was misleading."""
    try:
        detail = resp.json().get('detail')
        return str(detail) if detail else None
    except Exception:
        return None


def _handle_http_error(resp: httpx.Response, name: str) -> None:
    if resp.status_code == 200:
        return
    detail = _server_detail(resp)
    messages = {
        401: '[red]Invalid or revoked API key.[/red] Run: [cyan]xcli config set api-key <key>[/cyan]',
        400: f'[red]{detail or "Bad request."}[/red]',
        404: f"[red]Service extension '[cyan]{name}[/cyan]' not found or version not published.[/red]",
        503: '[red]Marketplace unavailable.[/red] Try again in a few moments.',
    }
    console.print(messages.get(resp.status_code, f'[red]HTTP {resp.status_code}:[/red] {detail or resp.text[:200]}'))
    raise typer.Exit(1)


def _marketplace_install(name: str, version: str) -> None:
    import io
    import zipfile

    api_key = get_api_key()
    if not api_key:
        console.print('[red]API key missing.[/red] Run: [cyan]xcli config set api-key xdk_...[/cyan] or [cyan]xcli login[/cyan]')
        raise typer.Exit(1)

    signing_key = get_signing_key()
    if not signing_key:
        console.print(
            '[red]Signing key missing.[/red] Run: [cyan]xcli config set signing-key <secret>[/cyan] or [cyan]xcli login[/cyan]\n'
            '[dim]Find your signing key at https://app.xcorehub.dev → Settings → Developer[/dim]'
        )
        raise typer.Exit(1)

    url = service_install_url(name, version)
    console.print(f'Downloading [cyan]{name}@{version}[/cyan]...')

    try:
        resp = httpx.get(url, headers={'X-API-Key': api_key}, timeout=30, follow_redirects=True)
    except httpx.RequestError as e:
        console.print(f'[red]Network error:[/red] {e}')
        raise typer.Exit(1)

    zip_bytes = resp.content
    _handle_http_error(resp, name)

    x_signature = resp.headers.get('X-Signature', '')
    x_service = resp.headers.get('X-Service', f'{name}@{version}')
    if not _verify_signature(zip_bytes, x_signature, signing_key):
        console.print(
            f'[red bold]✗ Invalid signature for {x_service}.[/red bold]\n'
            '[red]Installation cancelled — no files extracted.[/red]'
        )
        raise typer.Exit(1)

    console.print(f'[green]✓[/green] HMAC signature verified — [dim]{x_service}[/dim]')

    services_root = services_dir()
    dest = services_root / name
    if dest.exists():
        import shutil
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    # Same GitHub-codeload-wrapper-folder stripping as the plugin installer
    # (see xcli/plugin/install_commands.py's own comment for the full
    # reasoning) — included from day one here, not retrofitted.
    dest_resolved = dest.resolve()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        members = archive.namelist()
        prefix = members[0].split('/')[0] + '/' if members and '/' in members[0] else ''
        for member in members:
            stripped = member[len(prefix):] if prefix and member.startswith(prefix) else member
            if not stripped:
                continue
            target = (dest_resolved / stripped).resolve()
            if not target.is_relative_to(dest_resolved):
                continue
            if member.endswith('/'):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))

    console.print(f'[green]✓[/green] [cyan]{x_service}[/cyan] installed in [dim]{dest}[/dim]')


def install(
    service_spec: str = typer.Argument(..., help='Service extension to install: name, name@latest, or name@1.2.3'),
    force: bool = typer.Option(False, '--force', '-f', help='Overwrite existing installation'),
) -> None:
    """Install a marketplace service extension.

    Examples:
        xcli service install my-service
        xcli service install my-service@1.2.3
    """
    if '@' in service_spec:
        name, version = service_spec.split('@', 1)
    else:
        name, version = service_spec, 'latest'

    dest = services_dir() / name
    if dest.exists() and not force:
        console.print(f'[yellow]{name}[/yellow] is already installed. Use [cyan]--force[/cyan] to overwrite.')
        raise typer.Exit(1)

    _marketplace_install(name, version)


def register(app: Typer) -> None:

    app.command('install')(install)

    @app.command('versions')
    def versions(name: str) -> None:
        """List available versions of a marketplace service extension."""
        from rich.table import Table

        from .marketplace_commands import _get, _LIST_PATH

        with console.status(f'Fetching versions for [cyan]{name}[/cyan]...'):
            data = _get(f'{_LIST_PATH}/{name}')

        items = (data or {}).get('versions') or []
        if not items:
            console.print(f"[yellow]No versions found for '[cyan]{name}[/cyan]'.[/yellow]")
            return

        table = Table(title=f'Versions — {name}')
        table.add_column('Version', style='cyan')
        table.add_column('Status', style='green')
        table.add_column('Stable', justify='center')
        table.add_column('Created', style='dim')
        for item in items:
            table.add_row(
                item.get('version', '?'),
                item.get('publish_status', '?'),
                '✅' if item.get('is_stable') else '',
                str(item.get('created_at', '—'))[:10],
            )
        console.print(table)
        console.print(f'\n[dim]Install: xcli service install {name}@<version>[/dim]')

    @app.command('remove')
    def remove(
        name: str,
        yes: bool = typer.Option(False, '--yes', '-y', help='Skip confirmation'),
    ) -> None:
        """Remove an installed service extension."""
        import shutil
        from rich.prompt import Confirm

        service_path = services_dir() / name
        if not service_path.exists():
            console.print(f"[red]Service extension '[cyan]{name}[/cyan]' not found.[/red]")
            raise typer.Exit(1)
        if not yes and not Confirm.ask(f"[bold red]⚠ Remove '[cyan]{name}[/cyan]'?[/]", default=False):
            console.print('Cancelled.')
            return
        shutil.rmtree(service_path)
        console.print(f'[green]✓[/green] Service extension [cyan]{name}[/cyan] removed.')

    @app.command('info')
    def info(name: str) -> None:
        """Show details of a locally installed service extension."""
        from rich.console import Group
        from rich.markup import escape
        from rich.panel import Panel
        from xcli._xcore import _require_xcore
        _require_xcore()
        from xcore.kernel.security.signature import is_signed
        from xcore.kernel.security.validation import ManifestValidator

        service_path = services_dir() / name
        if not service_path.exists():
            console.print(f"[red]Service extension '[cyan]{name}[/cyan]' not found.[/red]")
            raise typer.Exit(1)

        try:
            manifest, _, _ = ManifestValidator().load_and_validate(service_path)
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

        console.print(
            Panel(
                Group(*lines),
                title=f'[bold green]🧩 {escape(manifest.name)} v{escape(manifest.version)}[/]',
                expand=False,
                border_style='cyan',
            )
        )

    @app.command('health')
    def health() -> None:
        """Health-check all installed service extensions (signature + AST + manifest)."""
        from rich.markup import escape
        from rich.table import Table
        from xcli._xcore import _require_xcore
        _require_xcore()
        from xcore.kernel.security.signature import is_signed
        from xcore.kernel.security.validation import ASTScanner, ManifestValidator

        services_root = services_dir()
        if not services_root.exists():
            console.print('[yellow]No service extensions found.[/yellow]')
            return
        entries = sorted(d for d in services_root.iterdir() if d.is_dir() and not d.name.startswith('_'))
        if not entries:
            console.print('[yellow]No service extensions found.[/yellow]')
            return

        table = Table(title='Service Extension Health Check')
        table.add_column('Extension', style='cyan', no_wrap=True)
        table.add_column('Mode', justify='center')
        table.add_column('Sig', justify='center')
        table.add_column('AST', justify='center')
        table.add_column('Manifest', justify='center')
        table.add_column('Status', style='dim')

        ok_count = err_count = 0
        with console.status('[green]Analyzing service extensions...'):
            for entry in entries:
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
