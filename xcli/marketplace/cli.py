import typer
from rich.console import Console
from typer import Typer

from xcli._run import ns, run
from xcli._xcore import _require_xcore

console = Console()
app = Typer(help="Plugin marketplace.")


@app.command("list")
def list_plugins() -> None:
    """List all plugins on the marketplace."""
    _require_xcore()
    console.print("[yellow]⚠[/yellow] Préfère [cyan]xcli plugin marketplace browse[/cyan] (même fonctionnalité).")
    from xcore.cli.marketplace_cmd import handle_marketplace
    run(handle_marketplace(ns(subcommand="list")))


@app.command("trending")
def trending() -> None:
    """Show trending plugins."""
    _require_xcore()
    console.print("[yellow]⚠[/yellow] Préfère [cyan]xcli plugin marketplace trending[/cyan] (même fonctionnalité).")
    from xcore.cli.marketplace_cmd import handle_marketplace
    run(handle_marketplace(ns(subcommand="trending")))


@app.command("search")
def search(query: str) -> None:
    """Search the marketplace."""
    _require_xcore()
    console.print("[yellow]⚠[/yellow] Préfère [cyan]xcli plugin marketplace search[/cyan] (même fonctionnalité).")
    from xcore.cli.marketplace_cmd import handle_marketplace
    run(handle_marketplace(ns(subcommand="search", query=query)))


@app.command("show")
def show(name: str) -> None:
    """Show details of a marketplace plugin."""
    _require_xcore()
    console.print("[yellow]⚠[/yellow] Préfère [cyan]xcli plugin marketplace info[/cyan] (même fonctionnalité).")
    from xcore.cli.marketplace_cmd import handle_marketplace
    run(handle_marketplace(ns(subcommand="show", name=name)))


@app.command("rate")
def rate(
    name: str,
    score: int = typer.Option(..., min=1, max=5, help="Score 1-5"),
) -> None:
    """Rate a marketplace plugin."""
    _require_xcore()
    console.print("[yellow]⚠[/yellow] Préfère [cyan]xcli plugin marketplace rate[/cyan] (même fonctionnalité).")
    from xcore.cli.marketplace_cmd import handle_marketplace
    run(handle_marketplace(ns(subcommand="rate", name=name, score=score)))
