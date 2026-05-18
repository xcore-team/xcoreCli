from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt

console = Console()

# ── YAML template (comments preserved) ───────────────────────

_TEMPLATE = """\
app:
  name: {name}
  env: {env}
  debug: {debug}
  secret_key: "{secret_key}"
  plugin_prefix: "/app"
  plugin_tags: []
  server_key: "{server_key}"
  server_key_iterations: 100000

  fastapi:
    title: "{name}"
    version: "0.1.0"
    docs_url: "/docs"
    redoc_url: "/redoc"
    openapi_url: "/openapi.json"
    redirect_slashes: true

  server:
    host: "0.0.0.0"
    port: 8000
    workers: 1
    reload: {reload}
    log_level: "{log_level}"
    proxy_headers: true
    forwarded_allow_ips: "*"

plugins:
  directory: {plugins_dir}
  secret_key: "{server_key}"
  strict_trusted: false
  interval: 10
  entry_point: src/main.py

services:
  databases:
    default:
      type: {db_type}
      url: {db_url}
      echo: false

  cache:
    backend: memory
    ttl: 300
    max_size: 1000

  scheduler:
    enabled: false
    backend: memory
    timezone: UTC

observability:
  logging:
    level: {log_level}
    format: "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
    file: log/app.log
    max_bytes: 10485760
    backup_count: 5
  metrics:
    enabled: false
    backend: memory
    prefix: {name}
  tracing:
    enabled: false
    backend: noop
    service_name: {name}
    endpoint: null

security:
  allowed_imports:
    - fastapi
    - json
    - re
    - math
    - datetime
    - typing
    - dataclasses
    - enum
    - functools
    - collections
    - hashlib
    - base64
    - asyncio
    - logging
    - uuid
  forbidden_imports: []
  rate_limit_default:
    calls: 100
    period_seconds: 60
"""

_DB_URL_DEFAULTS = {
    "sqlite":     "sqlite:///./xcore.db",
    "sqlasync":   "sqlite+aiosqlite:///./xcore.db",
    "postgresql": "postgresql+asyncpg://user:pass@localhost:5432/dbname",
    "mysql":      "mysql+aiomysql://user:pass@localhost:3306/dbname",
    "mongodb":    "mongodb://localhost:27017",
    "redis":      "redis://localhost:6379/0",
}


def _app() -> None:
    console.print("\n[bold]xcli init[/bold]  [dim]— Enter to keep defaults[/dim]\n")

    name       = Prompt.ask("App name",      default="xcore-app")
    env        = Prompt.ask("Environment",   choices=["development", "production"], default="development")
    secret_key = Prompt.ask("Secret key",    default="change-me-in-production", password=True)
    server_key = Prompt.ask("Server key",    default="change-me-in-production", password=True)
    db_type    = Prompt.ask("Database type", choices=list(_DB_URL_DEFAULTS), default="sqlasync")
    db_url     = Prompt.ask("Database URL",  default=_DB_URL_DEFAULTS[db_type])
    plugins_dir = Prompt.ask("Plugins dir",  default="./app")

    is_dev  = env == "development"
    content = _TEMPLATE.format(
        name=name,
        env=env,
        debug="true" if is_dev else "false",
        secret_key=secret_key,
        server_key=server_key,
        reload="true" if is_dev else "false",
        log_level="DEBUG" if is_dev else "INFO",
        plugins_dir=plugins_dir,
        db_type=db_type,
        db_url=db_url,
    )

    filename = Prompt.ask("\nSave as", default="integration")
    path = Path(filename.split(".")[0] + ".yaml")
    path.write_text(content, encoding="utf-8")

    console.print(f"\n[green]✓[/green] [cyan]{path}[/cyan] created.")
