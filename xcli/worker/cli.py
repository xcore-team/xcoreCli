from typing import Optional

import typer
from typer import Typer

from xcli._run import ns

_CTX = {"help_option_names": ["-h", "--help"]}
app = Typer(help="Manage Celery workers and background tasks.", context_settings=_CTX)
process_app = Typer(help="Fine-grained control over worker processes.", context_settings=_CTX)
app.add_typer(process_app, name="process")


# ── Top-level worker commands ─────────────────────────────────


@app.command("start")
def start(
    target: str = typer.Argument("celery", help="celery | all"),
    detach: bool = typer.Option(False, "--detach", "-d", help="Run in background"),
    loglevel: str = typer.Option("info", "--loglevel", "-l"),
    queues: Optional[str] = typer.Option(None, "-Q", help="Comma-separated queue names"),
    concurrency: Optional[int] = typer.Option(None, "-c", help="Worker concurrency"),
    hostname: Optional[str] = typer.Option(None, "-n", help="Worker hostname"),
) -> None:
    """Start a Celery worker (use `manager start` to start the API server)."""
    from .worker import handle_worker

    handle_worker(
        ns(
            worker_subcommand="start",
            target=target,
            detach=detach,
            reload=False,
            workers=1,
            loglevel=loglevel,
            queues=queues,
            concurrency=concurrency,
            hostname=hostname,
            app="main:app",
            host="0.0.0.0",
            port=8000,
        )
    )


@app.command("beat")
def beat(
    detach: bool = typer.Option(False, "--detach", "-d"),
    loglevel: str = typer.Option("info", "--loglevel", "-l"),
    schedule: Optional[str] = typer.Option(
        None, "--schedule", "-S", help="Beat schedule database file"
    ),
) -> None:
    """Start the Celery Beat scheduler for periodic tasks."""
    from .worker import handle_worker

    handle_worker(
        ns(
            worker_subcommand="beat",
            detach=detach,
            loglevel=loglevel,
            schedule=schedule,
        )
    )


@app.command("inspect")
def inspect() -> None:
    """List registered Celery tasks and active worker nodes."""
    from .worker import handle_worker

    handle_worker(ns(worker_subcommand="inspect"))


@app.command("purge")
def purge(
    queue: str = typer.Argument("default", help="Queue name to purge"),
) -> None:
    """Purge all messages from a Celery queue."""
    from .worker import handle_worker

    handle_worker(ns(worker_subcommand="purge", queue=queue))


# ── process sub-group ─────────────────────────────────────────


@process_app.command("start")
def process_start(
    count: int = typer.Option(1, "--count", "-c", help="Number of worker instances to start"),
    queues: Optional[str] = typer.Option(None, "--queues", "-Q", help="Comma-separated queues"),
    concurrency: Optional[int] = typer.Option(None, "--concurrency", help="Child processes per worker"),
    detach: bool = typer.Option(False, "--detach", "-d", help="Run in background"),
    loglevel: str = typer.Option("info", "--loglevel", "-l"),
) -> None:
    """Start one or more worker instances.

    Examples:
        xcli worker process start --count 4
        xcli worker process start --queues emails,priority --concurrency 8
    """
    from .worker import handle_worker

    for i in range(count):
        hostname = f"worker{i + 1}@%h" if count > 1 else None
        handle_worker(
            ns(
                worker_subcommand="start",
                target="celery",
                detach=detach,
                reload=False,
                workers=1,
                loglevel=loglevel,
                queues=queues,
                concurrency=concurrency,
                hostname=hostname,
                app="main:app",
                host="0.0.0.0",
                port=8000,
            )
        )


@process_app.command("stop")
def process_stop() -> None:
    """Gracefully shut down all running worker processes."""
    from .worker import handle_worker

    handle_worker(ns(worker_subcommand="stop", target="celery"))


@process_app.command("restart")
def process_restart(
    loglevel: str = typer.Option("info", "--loglevel", "-l"),
) -> None:
    """Stop then restart all worker processes."""
    from .worker import handle_worker

    handle_worker(ns(worker_subcommand="stop", target="celery"))
    handle_worker(
        ns(
            worker_subcommand="start",
            target="celery",
            detach=True,
            reload=False,
            workers=1,
            loglevel=loglevel,
            queues=None,
            concurrency=None,
            hostname=None,
            app="main:app",
            host="0.0.0.0",
            port=8000,
        )
    )


@process_app.command("status")
def process_status() -> None:
    """Show running worker processes with PID and resource usage."""
    from .worker import handle_worker

    handle_worker(ns(worker_subcommand="status", json=False))


@process_app.command("logs")
def process_logs(
    lines: int = typer.Option(50, "--lines", "-n", help="Number of lines to show"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Stream new log lines"),
) -> None:
    """Tail worker process logs."""
    from .worker import handle_worker

    handle_worker(
        ns(worker_subcommand="logs", target="celery", lines=lines, follow=follow)
    )
