import typer
from typer import Typer

from xcli._run import ns, run

app = Typer(help="Plugin marketplace.")


@app.command("list")
def list_plugins() -> None:
    """List all plugins on the marketplace."""
    from xcore.cli.marketplace_cmd import handle_marketplace
    run(handle_marketplace(ns(subcommand="list")))


@app.command("trending")
def trending() -> None:
    """Show trending plugins."""
    from xcore.cli.marketplace_cmd import handle_marketplace
    run(handle_marketplace(ns(subcommand="trending")))


@app.command("search")
def search(query: str) -> None:
    """Search the marketplace."""
    from xcore.cli.marketplace_cmd import handle_marketplace
    run(handle_marketplace(ns(subcommand="search", query=query)))


@app.command("show")
def show(name: str) -> None:
    """Show details of a marketplace plugin."""
    from xcore.cli.marketplace_cmd import handle_marketplace
    run(handle_marketplace(ns(subcommand="show", name=name)))


@app.command("rate")
def rate(
    name: str,
    score: int = typer.Option(..., min=1, max=5, help="Score 1-5"),
) -> None:
    """Rate a marketplace plugin."""
    from xcore.cli.marketplace_cmd import handle_marketplace
    run(handle_marketplace(ns(subcommand="rate", name=name, score=score)))
