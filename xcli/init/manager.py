from __future__ import annotations

import secrets
from pathlib import Path

from rich.console import Console

console = Console()

# ── DB defaults ───────────────────────────────────────────────

_DB_URLS: dict[str, str] = {
    "sqlite":     "sqlite+aiosqlite:///./xcore.db",
    "postgresql": "postgresql+asyncpg://user:pass@localhost:5432/dbname",
    "mysql":      "mysql+aiomysql://user:pass@localhost:3306/dbname",
    "mariadb":    "mysql+aiomysql://user:pass@localhost:3306/dbname",
}

# ── File templates ────────────────────────────────────────────

_INTEGRATION_YAML = """\
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
    - pydantic
  forbidden_imports: []
  rate_limit_default:
    calls: 100
    period_seconds: 60

marketplace:
  url: "https://marketplace.xcore.dev"
  api_url: "https://api.xcorehub.dev"
  timeout: 10
  cache_ttl: 300
"""

_MAIN_PY = """\
from contextlib import asynccontextmanager

from fastapi import FastAPI
from xcore import Xcore

xcore = Xcore(config_path="integration.yaml")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await xcore.boot(app)
    yield
    await xcore.shutdown()


app = FastAPI(
    title="{name}",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {{"status": "ok"}}
"""

_GITIGNORE = """\
__pycache__/
*.py[cod]
*.egg-info/
.env
.venv/
venv/
dist/
build/
*.db
*.sqlite3
log/
.DS_Store
"""

_REQUIREMENTS = """\
xcore
fastapi
uvicorn[standard]
sqlalchemy
aiosqlite
pydantic
"""

_DOTENV = """\
SECRET_KEY={secret_key}
SERVER_KEY={server_key}
DATABASE_URL={db_url}
"""

_README = """\
# {name}

Projet xcore généré avec `xcli init`.

## Démarrage

```bash
pip install -r requirements.txt
xcli manager start --reload
```

## Endpoints

- API docs : http://localhost:8000/docs
- Health   : http://localhost:8000/health

## Commandes utiles

```bash
xcli plugin new <nom>        # Créer un plugin
xcli plugin list             # Lister les plugins
xcli health                  # Vérifier les services
xcli manager top             # Dashboard live
xcli migration init          # Initialiser Alembic
```
"""


# ── Public API ────────────────────────────────────────────────

def create_project(
    name: str,
    *,
    env: str = "development",
    db_type: str = "sqlite",
    db_url: str | None = None,
    plugins_dir: str = "./app",
    output_dir: str | None = None,
) -> Path:
    """Scaffold a full xcore project. Returns the created root path."""
    secret_key = secrets.token_hex(32)
    server_key = secrets.token_hex(32)
    is_dev     = env == "development"
    log_level  = "DEBUG" if is_dev else "INFO"
    resolved_db_url = db_url or _DB_URLS.get(db_type, _DB_URLS["sqlite"])

    root = Path(output_dir or f"./{name}").resolve()
    root.mkdir(parents=True, exist_ok=True)

    _write(root / "integration.yaml", _INTEGRATION_YAML.format(
        name=name,
        env=env,
        debug="true" if is_dev else "false",
        secret_key=secret_key,
        server_key=server_key,
        reload="true" if is_dev else "false",
        log_level=log_level,
        plugins_dir=plugins_dir,
        db_type=db_type,
        db_url=resolved_db_url,
    ))
    _write(root / "main.py",          _MAIN_PY.format(name=name))
    _write(root / ".gitignore",       _GITIGNORE)
    _write(root / "requirements.txt", _REQUIREMENTS)
    _write(root / ".env",             _DOTENV.format(
        secret_key=secret_key,
        server_key=server_key,
        db_url=resolved_db_url,
    ))
    _write(root / "README.md", _README.format(name=name))

    # Directories
    plugins_path = root / plugins_dir.lstrip("./")
    plugins_path.mkdir(parents=True, exist_ok=True)
    (plugins_path / ".gitkeep").touch()

    log_path = root / "log"
    log_path.mkdir(parents=True, exist_ok=True)
    (log_path / ".gitkeep").touch()

    return root


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

