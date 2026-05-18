from typer import Typer

from .manager import _app

app = Typer()


@app.command()
def init() -> None:
    """Initialize a new xcore project — generates integration.yaml."""
    _app()
