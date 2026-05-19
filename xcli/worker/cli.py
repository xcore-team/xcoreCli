from typing import Optional

import typer
from typer import Typer

from xcli._run import ns

_CTX = {"help_option_names": ["-h", "--help"]}
app = Typer(help="Manage FastAPI and Celery processes.", context_settings=_CTX)


@app.command("start")
def start(
    target: str = typer.Argument("all", help="api | celery | all"),
    detach: bool = typer.Option(False, "--detach", "-d", help="Run in background"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Auto-reload (dev)"),
    workers: int = typer.Option(1, "--workers", "-w"),
    loglevel: str = typer.Option("info", "--loglevel", "-l"),
    queues: Optional[str] = typer.Option(None, "-Q", help="Celery queues"),
    concurrency: Optional[int] = typer.Option(None, "-c"),
    hostname: Optional[str] = typer.Option(None, "-n"),
) -> None:
    """Start FastAPI and/or Celery worker."""
    from .worker import handle_worker

    handle_worker(
        ns(
            worker_subcommand="start",
            target=target,
            detach=detach,
            reload=reload,
            workers=workers,
            loglevel=loglevel,
            queues=queues,
            concurrency=concurrency,
            hostname=hostname,
            app="main:app",
            host="0.0.0.0",
            port=8000,
        )
    )


@app.command("stop")
def stop(
    target: str = typer.Argument("all", help="api | celery | all"),
) -> None:
    """Stop running processes."""
    from .worker import handle_worker

    handle_worker(ns(worker_subcommand="stop", target=target))


@app.command("status")
def status() -> None:
    """Show process status."""
    from xcore.cli.worker_cmd import handle_worker

    handle_worker(ns(worker_subcommand="status", json=False))


@app.command("logs")
def logs(
    target: str = typer.Argument("all", help="api | celery | all"),
    lines: int = typer.Option(50, "--lines", "-n"),
    follow: bool = typer.Option(False, "--follow", "-f"),
) -> None:
    """Show process logs."""
    from xcore.cli.worker_cmd import handle_worker

    handle_worker(
        ns(worker_subcommand="logs", target=target, lines=lines, follow=follow)
    )


@app.command("inspect")
def inspect() -> None:
    """List registered Celery tasks and active workers."""
    from .worker import handle_worker

    handle_worker(ns(worker_subcommand="inspect"))


@app.command("purge")
def purge(
    queue: str = typer.Argument("default", help="Queue name to purge"),
) -> None:
    """Purge a Celery queue."""
    from .worker import handle_worker

    handle_worker(ns(worker_subcommand="purge", queue=queue))


@app.command("beat")
def beat(
    detach: bool = typer.Option(False, "--detach", "-d"),
    loglevel: str = typer.Option("info", "--loglevel", "-l"),
    schedule: Optional[str] = typer.Option(
        None, "--schedule", "-S", help="Beat schedule database file"
    ),
) -> None:
    """Start Celery Beat scheduler."""
    from .worker import handle_worker

    handle_worker(
        ns(
            worker_subcommand="beat",
            detach=detach,
            loglevel=loglevel,
            schedule=schedule,
        )
    )
