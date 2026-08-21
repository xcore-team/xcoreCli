from __future__ import annotations

import asyncio
from typing import Optional

import httpx
import typer
import yaml
from typer import Typer

from xcli._credentials import get_api_key, get_signing_key

from .shared import console, marketplace_install_url, plugins_dir


def _verify_signature(zip_bytes: bytes, x_signature: str, signing_key: str) -> bool:
    import hashlib
    import hmac as _hmac

    if not x_signature or ':' not in x_signature:
        return False
    algo, _, received_hex = x_signature.partition(':')
    if algo != 'hmac_sha256':
        return False
    expected = _hmac.new(signing_key.encode(), zip_bytes, hashlib.sha256).hexdigest()
    return _hmac.compare_digest(expected, received_hex)


def _server_detail(resp: httpx.Response) -> str | None:
    """Extracts FastAPI's `{"detail": "..."}` body, if present — the server
    already returns a specific, actionable message for 400s (missing signing
    key, un-tagged version, invalid GitHub token, ...); showing a single
    hardcoded guess for every 400 regardless of cause was misleading."""
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
        404: f"[red]Plugin '[cyan]{name}[/cyan]' not found or version not published.[/red]",
        503: '[red]Marketplace unavailable.[/red] Try again in a few moments.',
    }
    console.print(messages.get(resp.status_code, f'[red]HTTP {resp.status_code}:[/red] {detail or resp.text[:200]}'))
    raise typer.Exit(1)


def _marketplace_install(name: str, version: str) -> None:
    import io
    import zipfile

    api_key = get_api_key()
    if not api_key:
        console.print('[red]API key missing.[/red] Run: [cyan]xcli config set api-key xdk_...[/cyan]')
        raise typer.Exit(1)

    signing_key = get_signing_key()
    if not signing_key:
        console.print(
            '[red]Signing key missing.[/red] Run: [cyan]xcli config set signing-key <secret>[/cyan]\n'
            '[dim]Find your signing key at https://app.xcorehub.dev → Settings → Developer[/dim]'
        )
        raise typer.Exit(1)

    url = marketplace_install_url(name, version)
    console.print(f'Downloading [cyan]{name}@{version}[/cyan]...')

    try:
        resp = httpx.get(url, headers={'X-API-Key': api_key}, timeout=30, follow_redirects=True)
    except httpx.RequestError as e:
        console.print(f'[red]Network error:[/red] {e}')
        raise typer.Exit(1)

    zip_bytes = resp.content
    _handle_http_error(resp, name)

    x_signature = resp.headers.get('X-Signature', '')
    x_plugin = resp.headers.get('X-Plugin', f'{name}@{version}')
    if not _verify_signature(zip_bytes, x_signature, signing_key):
        console.print(
            f'[red bold]✗ Invalid signature for {x_plugin}.[/red bold]\n'
            '[red]Installation cancelled — no files extracted.[/red]'
        )
        raise typer.Exit(1)

    console.print(f'[green]✓[/green] HMAC signature verified — [dim]{x_plugin}[/dim]')

    plugins_root = plugins_dir()
    dest = plugins_root / name
    if dest.exists():
        import shutil
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    # Plugins published from a GitHub tag are re-downloaded server-side as a
    # GitHub codeload archive, which always wraps its contents in a single
    # top-level `{owner}-{repo}-{sha}/` folder — `extractall(plugins_root)`
    # used to dump that wrapper folder as-is, so the plugin ended up at
    # plugins_root/{owner}-{repo}-{sha}/ instead of the plugins_root/{name}
    # this function's own success message claimed, breaking `info`/`health`/
    # `remove` (which look up plugins_root/{name}) and leaking one stale
    # wrapper folder per version on every reinstall. Strip it exactly like
    # _install_from_url already does below, and extract into dest directly.
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

    console.print(f'[green]✓[/green] [cyan]{x_plugin}[/cyan] installed in [dim]{dest}[/dim]')


def _install_from_url(name: str, url: str, source_type: str) -> None:
    import io
    import zipfile

    plugins_root = plugins_dir()
    dest = plugins_root / name
    if dest.exists():
        import shutil
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    if source_type == 'git' or url.endswith('.git'):
        import subprocess

        console.print(f'  Cloning [dim]{url}[/dim]...')
        result = subprocess.run(['git', 'clone', '--depth=1', url, str(dest)], capture_output=True)
        if result.returncode != 0:
            console.print(f'[red]git clone failed:[/red] {result.stderr.decode().strip()}')
            raise typer.Exit(1)
    else:
        import urllib.request

        console.print(f'  Downloading [dim]{url}[/dim]...')
        try:
            data = urllib.request.urlopen(url, timeout=30).read()
        except Exception as e:
            console.print(f'[red]Download failed:[/red] {e}')
            raise typer.Exit(1)

        dest_resolved = dest.resolve()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
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

    console.print(f'[green]✓[/green] [cyan]{name}[/cyan] installed in [dim]{dest}[/dim]')


# Module-level (not a closure inside register()) so the exact same function
# object can be registered a second time as the top-level `xcli install`
# shortcut in xcli/main.py — one implementation, zero duplicated logic.
def install(
    plugin_spec: str = typer.Argument(..., help='Plugin to install: name, name@latest, or name@1.2.3'),
    source: str = typer.Option('marketplace', '--source', '-s', help='marketplace | git | zip'),
    url: Optional[str] = typer.Option(None, '--url', '-u', help='URL for git/zip source'),
    force: bool = typer.Option(False, '--force', '-f', help='Overwrite existing installation'),
    no_deps: bool = typer.Option(False, '--no-deps', help='Skip dependency installation'),
) -> None:
    """Install a plugin from marketplace, a Git URL, or a local zip.

    Examples:
        xcli plugin install my-plugin
        xcli plugin install my-plugin@1.2.3
        xcli plugin install my-plugin --source git --url https://github.com/user/plugin.git
    """
    if '@' in plugin_spec:
        name, version = plugin_spec.split('@', 1)
    else:
        name, version = plugin_spec, 'latest'

    dest = plugins_dir() / name
    if dest.exists() and not force:
        console.print(f'[yellow]{name}[/yellow] is already installed. Use [cyan]--force[/cyan] to overwrite.')
        raise typer.Exit(1)

    if source == 'marketplace':
        _marketplace_install(name, version)
        return
    if not url:
        console.print('[red]--url required for git/zip source.[/red]')
        raise typer.Exit(1)
    _install_from_url(name, url, source)


def register(app: Typer) -> None:

    app.command('install')(install)

    @app.command('versions')
    def versions(name: str) -> None:
        """List available versions of a marketplace plugin.

        The backend has no dedicated /versions endpoint — versions come
        embedded in GET /plugins/{slug} (see .marketplace_commands._get),
        so this reuses that same fetch rather than a separate client.
        """
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
        console.print(f'\n[dim]Install: xcli plugin install {name}@<version>[/dim]')

    @app.command('remove')
    def remove(
        name: str,
        yes: bool = typer.Option(False, '--yes', '-y', help='Skip confirmation'),
    ) -> None:
        """Remove an installed plugin."""
        import shutil
        from rich.prompt import Confirm

        plugin_path = plugins_dir() / name
        if not plugin_path.exists():
            console.print(f"[red]Plugin '[cyan]{name}[/cyan]' not found.[/red]")
            raise typer.Exit(1)
        if not yes and not Confirm.ask(f"[bold red]⚠ Remove '[cyan]{name}[/cyan]'?[/]", default=False):
            console.print('Cancelled.')
            return
        shutil.rmtree(plugin_path)
        console.print(f'[green]✓[/green] Plugin [cyan]{name}[/cyan] removed.')

    @app.command('info')
    def info(name: str) -> None:
        """Show details of a locally installed plugin."""
        from rich.console import Group
        from rich.markup import escape
        from rich.panel import Panel
        from xcli._xcore import _require_xcore
        _require_xcore()
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

    @app.command('health')
    def health() -> None:
        """Health-check all installed plugins (signature + AST + manifest)."""
        from rich.markup import escape
        from rich.table import Table
        from xcli._xcore import _require_xcore
        _require_xcore()
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
