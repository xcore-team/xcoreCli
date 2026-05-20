from __future__ import annotations

import asyncio
from typing import Optional

import httpx
import typer
import yaml
from rich.prompt import Confirm
from typer import Typer

from xcli._credentials import get_api_key, get_signing_key
from xcli._run import run

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


def _handle_http_error(resp: httpx.Response, name: str) -> None:
    if resp.status_code == 200:
        return
    messages = {
        401: '[red]Clé API invalide ou révoquée.[/red] Relancez : [cyan]xcli config set api-key <clé>[/cyan]',
        400: '[red]Signing key non configurée côté marketplace.[/red] Allez sur https://app.xcorehub.dev → Settings → Développeur',
        404: f"[red]Plugin '[cyan]{name}[/cyan]' introuvable ou version non publiée.[/red]",
        503: '[red]Marketplace indisponible.[/red] Réessayez dans quelques instants.',
    }
    console.print(messages.get(resp.status_code, f'[red]HTTP {resp.status_code}:[/red] {resp.text[:200]}'))
    raise typer.Exit(1)


def _marketplace_install(name: str, version: str) -> None:
    import io
    import zipfile

    api_key = get_api_key()
    if not api_key:
        console.print('[red]API key manquante.[/red] Lancez : [cyan]xcli config set api-key xdk_...[/cyan]')
        raise typer.Exit(1)

    signing_key = get_signing_key()
    if not signing_key:
        console.print(
            '[red]Signing key manquante.[/red] Lancez : [cyan]xcli config set signing-key <secret>[/cyan]\n'
            '[dim]Trouvez votre signing key sur https://app.xcorehub.dev → Settings → Développeur[/dim]'
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
            f'[red bold]✗ Signature invalide pour {x_plugin}.[/red bold]\n'
            '[red]Installation annulée — aucun fichier extrait.[/red]'
        )
        raise typer.Exit(1)

    console.print(f'[green]✓[/green] Signature HMAC vérifiée — [dim]{x_plugin}[/dim]')

    plugins_root = plugins_dir()
    dest = plugins_root / name
    if dest.exists():
        import shutil
        shutil.rmtree(dest)

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        archive.extractall(plugins_root)

    console.print(f'[green]✓[/green] [cyan]{x_plugin}[/cyan] installé dans [dim]{dest}[/dim]')


def _marketplace_client():
    from xcore.configurations.loader import ConfigLoader
    from xcore.marketplace import MarketplaceClient
    return MarketplaceClient(ConfigLoader.load(None))


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



def register(app: Typer) -> None:
    @app.command('install')
    def install(
        plugin_spec: str = typer.Argument(..., help='Plugin to install: name, name@latest, or name@1.2.3'),
        source: str = typer.Option('marketplace', '--source', '-s', help='marketplace | git | zip'),
        url: Optional[str] = typer.Option(None, '--url', '-u', help='URL for git/zip source'),
    ) -> None:
        """Install a plugin — supports name@version syntax for marketplace."""
        if '@' in plugin_spec:
            name, version = plugin_spec.split('@', 1)
        else:
            name, version = plugin_spec, 'latest'

        if source == 'marketplace':
            _marketplace_install(name, version)
            return
        if not url:
            console.print('[red]--url required for git/zip source.[/red]')
            raise typer.Exit(1)
        _install_from_url(name, url, source)

    @app.command('versions')
    def versions(name: str) -> None:
        """List available versions of a marketplace plugin."""

        async def _run() -> None:
            from rich.table import Table

            client = _marketplace_client()
            with console.status(f'Fetching versions for [cyan]{name}[/cyan]...'):
                data = await client.get_versions(name)

            if not data:
                console.print(f"[yellow]No versions found for '[cyan]{name}[/cyan]'.[/yellow]")
                return

            table = Table(title=f'Versions — {name}')
            table.add_column('Version', style='cyan')
            table.add_column('Released', style='dim')
            table.add_column('Source', style='green')
            table.add_column('Download URL', style='dim', no_wrap=False)
            for item in data:
                table.add_row(
                    item.get('version', '?'),
                    item.get('released_at', '—'),
                    item.get('source_type', 'zip'),
                    item.get('download_url', '—'),
                )
            console.print(table)
            console.print(f'\n[dim]Install: xcli plugin install {name}@<version>[/dim]')

        run(_run())

