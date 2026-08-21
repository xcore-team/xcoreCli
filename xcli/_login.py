from __future__ import annotations

import time
import webbrowser

import httpx
import typer
from rich.console import Console

from xcli._credentials import save_credential
from xcli.plugin.shared import marketplace_api_base

console = Console()

_START_PATH = '/app/xdevkeys/device/start'
_POLL_PATH = '/app/xdevkeys/device/poll'


def _try_open(url: str) -> bool:
    try:
        return webbrowser.open(url)
    except Exception:
        return False


def login() -> None:
    """`xcli login` — device-code flow (RFC 8628): opens the marketplace in a
    browser for the user to confirm a 6-digit code, then polls until the
    marketplace hands back a personal API key + signing key, saved straight
    into ~/.xcli/config.json (same store `xcli config set` writes to — this
    is just that, automated). The raw secrets are never printed."""
    base = marketplace_api_base()

    try:
        resp = httpx.post(f'{base}{_START_PATH}', timeout=15)
        resp.raise_for_status()
    except httpx.RequestError as e:
        console.print(f'[red]Network error:[/red] {e}')
        raise typer.Exit(1)
    except httpx.HTTPStatusError as e:
        console.print(f'[red]HTTP {e.response.status_code}:[/red] {e.response.text[:200]}')
        raise typer.Exit(1)

    data = resp.json()
    device_code = data['device_code']
    user_code = data['user_code']
    verification_uri = data['verification_uri']
    expires_in = data['expires_in']
    interval = data['interval']
    complete_url = f'{verification_uri}?code={user_code}'

    console.print(f"\nTo authorize this device, visit: [cyan]{verification_uri}[/cyan]")
    console.print(f"And enter code: [bold yellow]{user_code}[/bold yellow]\n")
    if not _try_open(complete_url):
        console.print("[dim]Couldn't open a browser automatically — open the URL above manually and enter the code.[/dim]\n")

    deadline = time.monotonic() + expires_in
    with console.status('Waiting for authorization...'):
        while time.monotonic() < deadline:
            time.sleep(interval)
            try:
                poll_resp = httpx.get(f'{base}{_POLL_PATH}', params={'device_code': device_code}, timeout=15)
            except httpx.RequestError:
                continue

            if poll_resp.status_code == 404:
                console.print('[red]Login request expired or was already used.[/red] Run [cyan]xcli login[/cyan] again.')
                raise typer.Exit(1)
            if poll_resp.status_code != 200:
                continue

            payload = poll_resp.json()
            if payload.get('status') == 'confirmed':
                save_credential('api-key', payload['api_key'])
                save_credential('signing-key', payload['signing_key'])
                console.print('[green]✓[/green] Logged in — credentials saved to [dim]~/.xcli/config.json[/dim]')
                return

    console.print('[red]Login timed out.[/red] Run [cyan]xcli login[/cyan] again.')
    raise typer.Exit(1)
