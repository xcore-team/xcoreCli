from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.markup import escape
from typer import Typer

from .shared import console


def register(app: Typer) -> None:
    @app.command('sign')
    def sign(
        path: str,
        key: Optional[str] = typer.Option(None, '--key', '-k', help='HMAC signing key (reads from config if omitted)'),
    ) -> None:
        """Sign a plugin with its HMAC key."""
        from xcore.kernel.security.signature import sign_plugin
        from xcore.kernel.security.validation import ManifestValidator

        plugin_path = Path(path)
        secret = (key or 'change-me').encode()
        try:
            manifest, _, _ = ManifestValidator().load_and_validate(plugin_path)
            signature = sign_plugin(manifest, secret)
            console.print(f'[green]✓[/green] Signed: [dim]{signature}[/dim]')
        except Exception as e:
            console.print(f'[red]Sign failed:[/red] {escape(str(e))}')
            raise typer.Exit(1)

    @app.command('verify')
    def verify(
        path: str,
        key: Optional[str] = typer.Option(None, '--key', '-k', help='HMAC signing key'),
    ) -> None:
        """Verify a plugin signature."""
        from xcore.kernel.security.signature import SignatureError, verify_plugin
        from xcore.kernel.security.validation import ManifestValidator

        plugin_path = Path(path)
        secret = (key or 'change-me').encode()
        try:
            manifest, _, _ = ManifestValidator().load_and_validate(plugin_path)
            verify_plugin(manifest, secret)
            console.print(f'[green]✓[/green] Signature valid: [cyan]{manifest.name}[/cyan]')
        except SignatureError as e:
            console.print(f'[red]✗ Invalid signature:[/red] {escape(str(e))}')
            raise typer.Exit(1)
        except Exception as e:
            console.print(f'[red]Error:[/red] {escape(str(e))}')
            raise typer.Exit(1)

    @app.command('validate')
    def validate(path: str) -> None:
        """Validate a plugin manifest."""
        from xcore.kernel.security.validation import ManifestValidator

        plugin_path = Path(path)
        try:
            manifest, _, _ = ManifestValidator().load_and_validate(plugin_path)
            console.print(
                f'[green]✓[/green] Valid manifest: [cyan]{manifest.name}[/cyan] '
                f'v{manifest.version} [{manifest.execution_mode.value}]'
            )
        except Exception as e:
            console.print(f'[red]✗ Invalid manifest:[/red] {escape(str(e))}')
            raise typer.Exit(1)
