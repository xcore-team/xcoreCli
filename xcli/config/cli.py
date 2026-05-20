import typer
from rich.console import Console
from typer import Typer

from xcli._credentials import get_api_key, get_signing_key, save_credential

_CTX = {"help_option_names": ["-h", "--help"]}
app = Typer(help="Manage xcli credentials and configuration.", context_settings=_CTX)
console = Console()

_VALID_KEYS = {"api-key", "signing-key"}


@app.command("set")
def config_set(
    key: str = typer.Argument(..., help="api-key | signing-key"),
    value: str = typer.Argument(..., help="Value to store"),
) -> None:
    """Store a credential locally in ~/.xcli/config.json."""
    if key not in _VALID_KEYS:
        console.print(f"[red]Unknown key '[cyan]{key}[/cyan]'. Valid: {', '.join(sorted(_VALID_KEYS))}[/red]")
        raise typer.Exit(1)
    save_credential(key, value)
    console.print(f"[green]✓[/green] [cyan]{key}[/cyan] saved to ~/.xcli/config.json")


@app.command("show")
def config_show() -> None:
    """Show current credential status (values are masked)."""
    api_key = get_api_key()
    signing_key = get_signing_key()
    console.print(f"api-key:     {'[green]set[/green]' if api_key else '[red]not set[/red]'}")
    console.print(f"signing-key: {'[green]set[/green]' if signing_key else '[red]not set[/red]'}")
    console.print("\n[dim]Set with: xcli config set api-key <value>[/dim]")
