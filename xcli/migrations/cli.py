from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from alembic import command
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from typer import Typer

from xcli.migrations.runtime import (
    BackupResult,
    backup_database,
    create_alembic_config,
    discover_models,
    get_backup_dir,
    get_database_url,
    get_scan_paths,
    list_backups,
    parse_db_url,
    project_root,
    render_discovery_summary,
    restore_database,
    run_alembic_command,
)

_CTX = {"help_option_names": ["-h", "--help"]}
app = Typer(help="Alembic migrations for xcore plugins.", context_settings=_CTX)
console = Console()
err = Console(stderr=True)

# ── Templates ──────────────────────────────────────────────────

_ENV_TEMPLATE = """\
from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
ROOT = Path(config.config_file_name).resolve().parent if config.config_file_name else Path.cwd()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from xcli.migrations.runtime import discover_models, get_database_url

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_database_url())
discovery = discover_models()
target_metadata = discovery.target_metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
"""

_SCRIPT_TEMPLATE = '''\
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
'''

_INI_TEMPLATE = """\
[alembic]
script_location = {script_location}
sqlalchemy.url = {database_url}

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""


# ── Helpers ────────────────────────────────────────────────────

def _alembic_dir(directory: str) -> Path:
    return (project_root() / directory).resolve()


def _ensure_initialized(directory: str) -> None:
    if not _alembic_dir(directory).exists():
        console.print(
            "[red]Alembic not initialized.[/red] Run [cyan]xcli migration init[/cyan] first."
        )
        raise typer.Exit(1)


def _print_backup(result: BackupResult) -> None:
    size_kb = result.size_bytes / 1024
    console.print(
        f"[green]✓[/green] Backup [cyan]{result.dialect}[/cyan] → "
        f"[dim]{result.path}[/dim] "
        f"[magenta]({size_kb:.1f} KB)[/magenta]"
    )


def _do_backup(label: str = "") -> None:
    prefix = f"[{label}] " if label else ""
    with console.status(f"{prefix}Creating backup..."):
        result = backup_database()
    _print_backup(result)


# ═══════════════════════════════════════════════════════════════
# Commands
# ═══════════════════════════════════════════════════════════════

@app.command("init")
def init(
    directory: str = typer.Option("alembic", "--dir", help="Alembic directory to create."),
    force: bool = typer.Option(False, "--force", help="Overwrite generated files if they already exist."),
) -> None:
    """Create an Alembic workspace wired to integration.yaml and all discovered models."""
    root = project_root()
    alembic_dir = _alembic_dir(directory)
    versions_dir = alembic_dir / "versions"
    ini_path = root / "alembic.ini"

    if alembic_dir.exists() and not force:
        console.print(
            f"[yellow]Already exists:[/yellow] [cyan]{alembic_dir}[/cyan] "
            "[dim](use --force to overwrite)[/dim]"
        )
        raise typer.Exit(1)

    with console.status("Scanning for SQLAlchemy models..."):
        discovery = discover_models()

    alembic_dir.mkdir(parents=True, exist_ok=True)
    versions_dir.mkdir(parents=True, exist_ok=True)

    (alembic_dir / "README").write_text(
        "Auto-generated by xcli migration init.\n", encoding="utf-8"
    )
    (alembic_dir / "env.py").write_text(_ENV_TEMPLATE, encoding="utf-8")
    (alembic_dir / "script.py.mako").write_text(_SCRIPT_TEMPLATE, encoding="utf-8")
    (alembic_dir / "__init__.py").write_text("", encoding="utf-8")

    db_url = get_database_url()
    ini_path.write_text(
        _INI_TEMPLATE.format(script_location=directory, database_url=db_url),
        encoding="utf-8",
    )

    db_info = parse_db_url(db_url)

    console.print(f"[green]✓[/green] Alembic initialized → [cyan]{alembic_dir}[/cyan]")
    console.print(f"[green]✓[/green] Config → [cyan]{ini_path}[/cyan]")
    console.print(f"[dim]Database:[/dim] [magenta]{db_info.dialect}[/magenta] {escape(db_info.host or db_info.database)}")
    console.print(f"[dim]Discovery:[/dim] {render_discovery_summary(discovery)}")

    _print_scan_paths()

    if discovery.warnings:
        console.print("[yellow]Warnings:[/yellow]")
        for w in discovery.warnings:
            console.print(f"  [yellow]·[/yellow] {escape(w)}")


@app.command("scan")
def scan(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show all scanned files."),
) -> None:
    """Preview all discovered SQLAlchemy models without generating anything."""
    with console.status("Scanning for SQLAlchemy models..."):
        discovery = discover_models()

    _print_scan_paths()

    table = Table(title=f"Discovered Models ({discovery.model_count} tables)")
    table.add_column("File", style="dim")
    table.add_column("Tables", style="cyan", justify="right")

    from xcli.migrations.runtime import _iter_python_files, _load_module, _extract_metadata

    root = project_root()
    for scan_path in get_scan_paths():
        for py_file in _iter_python_files(scan_path):
            try:
                module = _load_module(py_file, scan_path)
                metas = _extract_metadata(module)
                if metas or verbose:
                    tables = [t for m in metas for t in m.tables]
                    if tables or verbose:
                        table.add_row(
                            str(py_file.relative_to(root)),
                            ", ".join(tables) if tables else "[dim]—[/dim]",
                        )
            except Exception:
                if verbose:
                    table.add_row(str(py_file.relative_to(root)), "[red]error[/red]")

    console.print(table)

    if discovery.warnings:
        console.print(f"\n[yellow]{len(discovery.warnings)} warning(s):[/yellow]")
        for w in discovery.warnings:
            console.print(f"  [yellow]·[/yellow] {escape(w)}")


@app.command("revision")
def revision(
    message: str = typer.Option(..., "--message", "-m", help="Revision message."),
    autogenerate: bool = typer.Option(
        True, "--autogenerate/--empty",
        help="Generate operations from discovered models.",
    ),
    directory: str = typer.Option("alembic", "--dir", help="Alembic directory."),
) -> None:
    """Create a new Alembic revision from discovered models."""
    _ensure_initialized(directory)
    with console.status("Scanning models..."):
        discovery = discover_models()
    console.print(f"[dim]Discovery:[/dim] {render_discovery_summary(discovery)}")
    run_alembic_command(directory, lambda cfg: command.revision(cfg, message=message, autogenerate=autogenerate))


@app.command("upgrade")
def upgrade(
    revision: str = typer.Argument("head", help="Target revision (head, +1, <id>)."),
    directory: str = typer.Option("alembic", "--dir", help="Alembic directory."),
    backup: bool = typer.Option(False, "--backup", "-b", help="Backup database before upgrading."),
) -> None:
    """Apply migrations up to the target revision."""
    _ensure_initialized(directory)
    if backup:
        _do_backup("pre-upgrade")
    run_alembic_command(directory, lambda cfg: command.upgrade(cfg, revision))


@app.command("downgrade")
def downgrade(
    revision: str = typer.Argument(..., help="Target revision (-1, base, <id>)."),
    directory: str = typer.Option("alembic", "--dir", help="Alembic directory."),
    backup: bool = typer.Option(True, "--backup/--no-backup", "-b", help="Backup database before downgrading."),
) -> None:
    """Rollback migrations to the target revision."""
    _ensure_initialized(directory)
    if backup:
        _do_backup("pre-downgrade")
    run_alembic_command(directory, lambda cfg: command.downgrade(cfg, revision))


@app.command("current")
def current(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    directory: str = typer.Option("alembic", "--dir"),
) -> None:
    """Show the current database revision."""
    _ensure_initialized(directory)
    run_alembic_command(directory, lambda cfg: command.current(cfg, verbose=verbose))


@app.command("history")
def history(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    directory: str = typer.Option("alembic", "--dir"),
) -> None:
    """Show migration history."""
    _ensure_initialized(directory)
    command.history(create_alembic_config(directory), verbose=verbose)


@app.command("heads")
def heads(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    directory: str = typer.Option("alembic", "--dir"),
) -> None:
    """Show migration heads."""
    _ensure_initialized(directory)
    command.heads(create_alembic_config(directory), verbose=verbose)


@app.command("stamp")
def stamp(
    revision: str = typer.Argument(..., help="Revision to stamp without running migrations."),
    directory: str = typer.Option("alembic", "--dir"),
) -> None:
    """Stamp the database at a revision without running migrations."""
    _ensure_initialized(directory)
    run_alembic_command(directory, lambda cfg: command.stamp(cfg, revision))


# ── Backup / Restore ───────────────────────────────────────────

@app.command("backup")
def backup_cmd(
    output_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Backup directory (default: migration.backup_dir)."),
) -> None:
    """Backup the database (SQLite / PostgreSQL / MySQL / MariaDB)."""
    dest = Path(output_dir).resolve() if output_dir else None
    db_url = get_database_url()
    info = parse_db_url(db_url)

    console.print(f"Database: [magenta]{info.dialect}[/magenta] [dim]{escape(info.host or info.database)}[/dim]")
    try:
        with console.status("Creating backup..."):
            result = backup_database(backup_dir=dest)
        _print_backup(result)
    except FileNotFoundError as e:
        err.print(f"[red]File not found:[/red] {escape(str(e))}")
        raise typer.Exit(1)
    except RuntimeError as e:
        err.print(f"[red]Backup failed:[/red] {escape(str(e))}")
        raise typer.Exit(1)


@app.command("restore")
def restore_cmd(
    backup_path: Optional[str] = typer.Argument(None, help="Path to backup file. Omit to pick latest."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Restore the database from a backup file."""
    from rich.prompt import Confirm

    if backup_path:
        path = Path(backup_path).resolve()
    else:
        backups = list_backups()
        if not backups:
            err.print(f"[red]No backups found in[/red] [cyan]{get_backup_dir()}[/cyan]")
            raise typer.Exit(1)
        path = backups[0]
        console.print(f"Latest backup: [cyan]{path}[/cyan]")

    if not path.exists():
        err.print(f"[red]Backup not found:[/red] {path}")
        raise typer.Exit(1)

    db_url = get_database_url()
    info = parse_db_url(db_url)

    console.print(f"[yellow]⚠[/yellow] This will overwrite [magenta]{info.dialect}[/magenta] database: [dim]{escape(info.host or info.database)}[/dim]")

    if not yes and not Confirm.ask("Proceed with restore?", default=False):
        console.print("Cancelled.")
        return

    try:
        with console.status(f"Restoring from [cyan]{path.name}[/cyan]..."):
            restore_database(path)
        console.print(f"[green]✓[/green] Database restored from [dim]{path}[/dim]")
    except Exception as e:
        err.print(f"[red]Restore failed:[/red] {escape(str(e))}")
        raise typer.Exit(1)


@app.command("backups")
def backups_cmd() -> None:
    """List available database backups."""
    backup_dir = get_backup_dir()
    items = list_backups(backup_dir)

    if not items:
        console.print(f"[yellow]No backups in[/yellow] [cyan]{backup_dir}[/cyan]")
        return

    table = Table(title=f"Backups — {backup_dir}")
    table.add_column("File", style="cyan")
    table.add_column("Size", justify="right", style="magenta")
    table.add_column("Date", style="dim")

    from datetime import datetime
    for p in items:
        stat = p.stat()
        size = f"{stat.st_size / 1024:.1f} KB"
        date = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        table.add_row(p.name, size, date)

    console.print(table)
    console.print(f"\n[dim]Restore: xcli migration restore <file>[/dim]")


# ── Internal helpers ───────────────────────────────────────────

def _print_scan_paths() -> None:
    paths = get_scan_paths()
    root = project_root()
    console.print("[dim]Scan paths:[/dim]")
    for p in paths:
        try:
            rel = p.relative_to(root)
        except ValueError:
            rel = p
        console.print(f"  [dim]·[/dim] [cyan]{rel}[/cyan]")
