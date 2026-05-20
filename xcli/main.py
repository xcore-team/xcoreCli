import asyncio

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from typer import Typer

from xcli._run import ns, run

_console = Console()
from xcli.init.manager import _app as _init_wizard
from xcli.init.upgrade import run_upgrade as _run_upgrade
from xcli.config.cli import app as config_app
from xcli.manager.cli import app as manager_app
from xcli.migrations.cli import app as migrations_app
from xcli.plugin.cli import app as plugin_app
from xcli.sandbox.cli import app as sandbox_app
from xcli.worker.cli import app as worker_app

_CTX = {"help_option_names": ["-h", "--help"]}

app = Typer(help="xcli — xcore project manager.", context_settings=_CTX)


# ── init ──────────────────────────────────────────────────────

@app.command()
def init() -> None:
    """Generate integration.yaml for a new xcore project."""
    _init_wizard()


# ── upgrade ───────────────────────────────────────────────────

@app.command()
def upgrade() -> None:
    """Migrate integration.yaml to the latest schema (adds missing keys, keeps existing values)."""
    _run_upgrade()


# ── health ────────────────────────────────────────────────────

@app.command()
def health() -> None:
    """Global health-check of all xcore services."""
    async def _run():
        from xcore.configurations.loader import ConfigLoader
        from xcore.services import ServiceContainer
        cfg = ConfigLoader.load(None)
        container = ServiceContainer(cfg.services)
        await container.init()
        result = await container.health()
        await container.shutdown()
        return result

    try:
        data = asyncio.run(_run())
    except Exception as e:
        _console.print(f"[red]Health check failed:[/red] {escape(str(e))}")
        raise typer.Exit(1)

    table = Table(box=None, show_header=False, padding=(0, 2))
    for svc, info in data["services"].items():
        sym = "✅" if info["ok"] else "❌"
        msg = info.get("msg", "")
        table.add_row(sym, f"[bold]{svc}[/]", f"[dim]{escape(msg)}[/]")

    ok = data.get("ok", False)
    status_str = "[bold green]OK[/]" if ok else "[bold red]DÉGRADÉ[/]"
    _console.print(Panel(table, title=f"Health Check : {status_str}", expand=False,
                         border_style="green" if ok else "red"))


# ── services ──────────────────────────────────────────────────

@app.command()
def services() -> None:
    """Show status of all xcore services."""
    async def _run():
        from xcore.configurations.loader import ConfigLoader
        from xcore.services import ServiceContainer
        cfg = ConfigLoader.load(None)
        container = ServiceContainer(cfg.services)
        await container.init()
        result = container.status()
        await container.shutdown()
        return result

    try:
        data = asyncio.run(_run())
    except Exception as e:
        _console.print(f"[red]Error:[/red] {escape(str(e))}")
        raise typer.Exit(1)

    table = Table(title="État des Services Système")
    table.add_column("Service", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Détails", style="dim")
    for svc_id, info in data["services"].items():
        st = info.get("status", "unknown")
        color = "green" if st == "ready" else ("yellow" if st in ("initializing", "uninitialized") else "red")
        details = ", ".join(f"{k}={v}" for k, v in info.items() if k not in ("name", "status"))
        table.add_row(info.get("name", svc_id), f"[{color}]{st}[/]", escape(details))
    _console.print(table)


# ── sub-apps ──────────────────────────────────────────────────

app.add_typer(config_app,  name="config")
app.add_typer(plugin_app,  name="plugin")
app.add_typer(sandbox_app, name="sandbox")
app.add_typer(worker_app,  name="worker")
app.add_typer(manager_app, name="manager")
app.add_typer(migrations_app, name="migration")

# ── short aliases (hidden) ────────────────────────────────────
app.add_typer(plugin_app,  name="p",  hidden=True)
app.add_typer(sandbox_app, name="sb", hidden=True)
app.add_typer(worker_app,  name="w",  hidden=True)
app.add_typer(manager_app, name="m",  hidden=True)
app.add_typer(migrations_app, name="mig", hidden=True)
