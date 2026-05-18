from pathlib import Path

import yaml
from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.rule import Rule

console = Console()


def _section(title: str) -> None:
    console.print()
    console.print(Rule(f"[bold cyan]{title}[/bold cyan]"))


# ── Sections ──────────────────────────────────────────────────


def _ask_app() -> dict:
    _section("Application")
    name = Prompt.ask("App name", default="xcore-app")
    env = Prompt.ask(
        "Environment",
        choices=["development", "staging", "production"],
        default="development",
    )
    debug = Confirm.ask("Enable debug mode", default=(env == "development"))
    secret_key = Prompt.ask(
        "Secret key  [dim](JWT / sessions)[/dim]",
        default="change-me-in-production",
        password=True,
    )
    server_key = Prompt.ask(
        "Server key  [dim](plugin signing)[/dim]",
        default="change-me-in-production",
        password=True,
    )
    server_key_iterations = IntPrompt.ask(
        "Server key PBKDF2 iterations", default=100_000
    )
    plugin_prefix = Prompt.ask("Plugin route prefix", default="/plugin")
    raw_tags = Prompt.ask(
        "Plugin OpenAPI tags  [dim](comma-separated)[/dim]", default="plugins"
    )
    plugin_tags = [t.strip() for t in raw_tags.split(",") if t.strip()]

    app: dict = {
        "name": name,
        "env": env,
        "debug": debug,
        "secret_key": secret_key,
        "server_key": server_key,
        "server_key_iterations": server_key_iterations,
        "plugin_prefix": plugin_prefix,
        "plugin_tags": plugin_tags,
    }

    if Confirm.ask("Configure FastAPI metadata?", default=False):
        _section("FastAPI")
        app["fastapi"] = {
            "title": Prompt.ask("API title", default=name),
            "version": Prompt.ask("API version", default="0.1.0"),
            "description": Prompt.ask("API description", default=""),
            "docs_url": Prompt.ask("Docs URL  [dim](empty to disable)[/dim]", default="/docs") or None,
            "redoc_url": Prompt.ask("ReDoc URL  [dim](empty to disable)[/dim]", default="/redoc") or None,
        }

    return app


def _ask_server() -> dict:
    _section("Server — Uvicorn")
    return {
        "host": Prompt.ask("Host", default="0.0.0.0"),
        "port": IntPrompt.ask("Port", default=8000),
        "workers": IntPrompt.ask("Workers", default=1),
        "reload": Confirm.ask("Auto-reload  [dim](dev only)[/dim]", default=False),
        "log_level": Prompt.ask(
            "Log level",
            choices=["debug", "info", "warning", "error", "critical"],
            default="info",
        ),
        "proxy_headers": Confirm.ask("Trust proxy headers", default=True),
    }


def _ask_plugins() -> dict:
    _section("Plugins")
    return {
        "directory": Prompt.ask("Plugins directory", default="./plugins"),
        "entry_point": Prompt.ask("Entry point inside each plugin", default="src/main.py"),
        "strict_trusted": Confirm.ask(
            "Require .sig signature file  [dim](strict_trusted)[/dim]", default=True
        ),
        "interval": IntPrompt.ask("File-watcher interval (seconds)", default=2),
        "secret_key": Prompt.ask(
            "Plugin secret key", default="change-me-in-production", password=True
        ),
    }


def _ask_databases() -> dict:
    _section("Databases")
    console.print("[dim]At least one database is required.[/dim]")
    databases: dict = {}

    while True:
        db_name = Prompt.ask("Database alias", default="default")
        db_type = Prompt.ask(
            "Type",
            choices=["sqlite", "sqlasync", "mysql", "postgresql", "mongodb", "redis"],
            default="sqlasync",
        )

        url_defaults = {
            "sqlite": "sqlite:///./xcore.db",
            "sqlasync": "sqlite+aiosqlite:///./xcore.db",
            "postgresql": "postgresql+asyncpg://user:pass@localhost:5432/dbname",
            "mysql": "mysql+aiomysql://user:pass@localhost:3306/dbname",
            "mongodb": "mongodb://localhost:27017",
            "redis": "redis://localhost:6379/0",
        }
        url = Prompt.ask("Connection URL", default=url_defaults[db_type])

        cfg: dict = {"type": db_type, "url": url}

        if db_type not in ("mongodb", "redis"):
            cfg["pool_size"] = IntPrompt.ask("Pool size", default=5)
            cfg["max_overflow"] = IntPrompt.ask("Max overflow", default=10)
            cfg["echo"] = Confirm.ask("Echo SQL  [dim](query logging)[/dim]", default=False)

        if db_type == "mongodb":
            cfg["database"] = Prompt.ask("MongoDB database name", default="xcore")

        if db_type == "redis":
            cfg["max_connections"] = IntPrompt.ask("Max connections", default=10)

        databases[db_name] = cfg

        if not Confirm.ask("Add another database?", default=False):
            break

    return databases


def _ask_cache() -> dict | None:
    _section("Cache")
    if not Confirm.ask("Configure cache?", default=False):
        return None
    backend = Prompt.ask("Backend", choices=["memory", "redis"], default="memory")
    cfg: dict = {
        "backend": backend,
        "ttl": IntPrompt.ask("TTL (seconds)", default=300),
        "max_size": IntPrompt.ask("Max size (entries)", default=1000),
    }
    if backend == "redis":
        cfg["url"] = Prompt.ask("Redis URL", default="redis://localhost:6379/2")
    return cfg


def _ask_scheduler() -> dict | None:
    _section("Scheduler")
    if not Confirm.ask("Enable scheduler?", default=False):
        return None
    backend = Prompt.ask(
        "Backend", choices=["memory", "redis", "database"], default="memory"
    )
    cfg: dict = {
        "enabled": True,
        "backend": backend,
        "timezone": Prompt.ask("Timezone", default="UTC"),
    }
    if backend == "redis":
        cfg["url"] = Prompt.ask("Redis URL", default="redis://localhost:6379/3")
    return cfg


def _ask_worker() -> dict | None:
    _section("Background Worker (xworker / Celery)")
    if not Confirm.ask("Enable background worker?", default=False):
        return None
    broker = Prompt.ask("Broker URL", default="redis://localhost:6379/0")
    backend = Prompt.ask("Result backend", default="redis://localhost:6379/1")
    concurrency = IntPrompt.ask("Concurrency", default=4)
    raw_queues = Prompt.ask("Task queues  [dim](comma-separated)[/dim]", default="default")
    queues = [q.strip() for q in raw_queues.split(",") if q.strip()]
    raw_modules = Prompt.ask(
        "Task modules to auto-discover  [dim](comma-separated, leave empty to skip)[/dim]",
        default="",
    )
    modules = [m.strip() for m in raw_modules.split(",") if m.strip()]
    cfg: dict = {
        "enabled": True,
        "broker_url": broker,
        "result_backend": backend,
        "concurrency": concurrency,
        "queues": queues,
        "task_default_queue": queues[0] if queues else "default",
    }
    if modules:
        cfg["modules"] = modules
    return cfg


def _ask_observability() -> dict | None:
    _section("Observability")
    if not Confirm.ask("Configure observability?", default=False):
        return None

    result: dict = {}

    # Logging
    _section("  Logging")
    log_level = Prompt.ask(
        "Log level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
    )
    log_file = Prompt.ask(
        "Log file path  [dim](empty = console only)[/dim]", default=""
    )
    logging_cfg: dict = {"level": log_level}
    if log_file:
        logging_cfg["file"] = log_file
        logging_cfg["max_bytes"] = IntPrompt.ask(
            "Max log file size (bytes)", default=10_485_760
        )
        logging_cfg["backup_count"] = IntPrompt.ask("Backup count", default=5)
    result["logging"] = logging_cfg

    # Metrics
    if Confirm.ask("Enable metrics?", default=False):
        backend = Prompt.ask(
            "Metrics backend",
            choices=["memory", "prometheus", "statsd"],
            default="prometheus",
        )
        prefix = Prompt.ask("Metrics prefix", default="xcore")
        result["metrics"] = {"enabled": True, "backend": backend, "prefix": prefix}

    # Tracing
    if Confirm.ask("Enable distributed tracing?", default=False):
        backend = Prompt.ask(
            "Tracing backend",
            choices=["opentelemetry", "jaeger"],
            default="opentelemetry",
        )
        result["tracing"] = {
            "enabled": True,
            "backend": backend,
            "service_name": Prompt.ask("Service name", default=name if (name := "") else "xcore"),
            "endpoint": Prompt.ask("Collector endpoint", default="http://localhost:4317"),
        }

    return result or None


def _ask_security() -> dict | None:
    _section("Security")
    if not Confirm.ask("Configure security settings?", default=False):
        return None

    calls = IntPrompt.ask("Rate limit — requests per period", default=100)
    period = IntPrompt.ask("Rate limit — period (seconds)", default=60)

    raw_forbidden = Prompt.ask(
        "Forbidden imports in plugins  [dim](comma-separated, empty = none)[/dim]",
        default="",
    )
    forbidden = [i.strip() for i in raw_forbidden.split(",") if i.strip()]

    cfg: dict = {"rate_limit_default": {"calls": calls, "period_seconds": period}}
    if forbidden:
        cfg["forbidden_imports"] = forbidden
    return cfg


def _ask_marketplace() -> dict | None:
    _section("Marketplace")
    if not Confirm.ask("Configure marketplace access?", default=False):
        return None
    return {
        "url": Prompt.ask("Marketplace URL", default="https://marketplace.xcore.dev"),
        "api_key": Prompt.ask("API key", default="", password=True),
        "timeout": IntPrompt.ask("Request timeout (seconds)", default=10),
        "cache_ttl": IntPrompt.ask("Cache TTL (seconds)", default=300),
    }


def _ask_cors() -> dict | None:
    _section("CORS")
    if not Confirm.ask("Configure CORS?", default=False):
        return None
    return {
        "cors_allow_credentials": Confirm.ask("Allow credentials", default=True),
        "cors_max_age": IntPrompt.ask("Max age (seconds)", default=3600),
        "cors_redirect_status": IntPrompt.ask("Redirect status code", default=307),
    }


# ── Entry point ───────────────────────────────────────────────


def _app() -> None:
    console.print()
    console.print(
        "[bold green]xcore project setup[/bold green]  "
        "[dim]— Press Enter to accept defaults[/dim]"
    )

    # Collect all sections
    app_cfg = _ask_app()
    app_cfg["server"] = _ask_server()

    plugins_cfg = _ask_plugins()
    databases = _ask_databases()

    services: dict = {"databases": databases}
    cache = _ask_cache()
    if cache:
        services["cache"] = cache
    scheduler = _ask_scheduler()
    if scheduler:
        services["scheduler"] = scheduler
    worker = _ask_worker()
    if worker:
        services["xworker"] = worker

    config: dict = {
        "app": app_cfg,
        "plugins": plugins_cfg,
        "services": services,
    }

    observability = _ask_observability()
    if observability:
        config["observability"] = observability

    security = _ask_security()
    if security:
        config["security"] = security

    marketplace = _ask_marketplace()
    if marketplace:
        config["marketplace"] = marketplace

    cors = _ask_cors()
    if cors:
        config.update(cors)

    # Preview & save
    console.print()
    console.print(Rule("[bold green]Configuration generated[/bold green]"))
    import json
    console.print_json(json.dumps(config, default=str))

    filename = Prompt.ask("\nSave as", default="integration")
    path = Path(filename.split(".")[0] + ".yaml")

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    console.print(f"\n[bold green]✓[/bold green] Saved to [cyan]{path}[/cyan]")
