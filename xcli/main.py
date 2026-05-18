from typer import Typer

from xcli._run import ns, run
from xcli.init.manager import _app as _init_wizard
from xcli.init.upgrade import run_upgrade as _run_upgrade
from xcli.manager.cli import app as manager_app
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
    from xcore.cli.plugin_cmd import handle_health
    run(handle_health(ns(json=False)))


# ── services ──────────────────────────────────────────────────

@app.command()
def services() -> None:
    """Show status of all xcore services."""
    from xcore.cli.plugin_cmd import handle_services
    run(handle_services(ns(subcommand="status", json=False)))


# ── sub-apps ──────────────────────────────────────────────────

app.add_typer(plugin_app,  name="plugin")
app.add_typer(sandbox_app, name="sandbox")
app.add_typer(worker_app,  name="worker")
app.add_typer(manager_app, name="manager")

# ── short aliases (hidden) ────────────────────────────────────
app.add_typer(plugin_app,  name="p",  hidden=True)
app.add_typer(sandbox_app, name="sb", hidden=True)
app.add_typer(worker_app,  name="w",  hidden=True)
app.add_typer(manager_app, name="m",  hidden=True)
