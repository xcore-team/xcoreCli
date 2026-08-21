from __future__ import annotations

import importlib.util
import inspect
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Iterator
from urllib.parse import urlparse

import yaml
from alembic.config import Config
from rich.console import Console
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

console = Console()

_CONFIG_CANDIDATES = (
    "integration.yaml",
    "integration.json",
    "config/integration.yaml",
    "config/integration.json",
)
_IGNORED_PARTS = {
    ".git", ".hg", ".svn", ".venv", "venv", "__pycache__",
    "node_modules", "dist", "build", "alembic", "migrations",
}


# ── Data classes ──────────────────────────────────────────────

@dataclass(slots=True)
class DiscoveryResult:
    target_metadata: list[MetaData]
    modules: list[str]
    warnings: list[str]
    model_count: int = 0


@dataclass(slots=True)
class DBInfo:
    dialect: str       # sqlite | postgresql | mysql | mariadb
    driver: str        # e.g. psycopg2, pymysql
    host: str
    port: int
    user: str
    password: str
    database: str
    url: str


@dataclass
class BackupResult:
    path: Path
    dialect: str
    size_bytes: int
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


# ── Config helpers ─────────────────────────────────────────────

def require_config_path() -> Path:
    for candidate in _CONFIG_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return path.resolve()
    console.print("[yellow]⚠[/yellow] No integration.yaml — run [cyan]xcli init[/cyan] first.")
    raise SystemExit(1)


def load_config() -> dict:
    path = require_config_path()
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def project_root() -> Path:
    return require_config_path().parent.resolve()


def plugins_root() -> Path:
    cfg = load_config()
    raw = cfg.get("plugins", {}).get("directory", "./app")
    root = Path(raw)
    if not root.is_absolute():
        root = project_root() / root
    return root.resolve()


def _load_project_dotenv(cfg: dict) -> None:
    """Mirrors xcore.configurations.loader.ConfigLoader._load_dotenv — reads
    the SAME `app.dotenv` key the running app itself uses to pick its .env
    file (e.g. `conf/.env`, not necessarily the project-root `.env` that
    `xcli init` scaffolds by default), so a hand-built or non-default-laid-out
    project resolves the same values the app would at runtime. Without this,
    `${DATABASE_URL}`-style placeholders in integration.yaml stayed literal
    strings — a valid YAML value, but useless to SQLAlchemy/alembic."""
    dotenv_file = cfg.get("app", {}).get("dotenv")
    if not dotenv_file:
        return
    path = Path(dotenv_file)
    if not path.is_absolute():
        path = project_root() / path
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=path, override=False)
    except ImportError:
        console.print(
            f"[yellow]⚠[/yellow] python-dotenv not installed — [dim]{path}[/dim] not loaded, "
            "${VAR} placeholders in integration.yaml may stay unresolved."
        )


def get_database_url() -> str:
    cfg = load_config()
    _load_project_dotenv(cfg)

    databases = cfg.get("services", {}).get("databases", {})
    if not databases:
        console.print("[red]No services.databases.* found in integration.yaml[/red]")
        raise SystemExit(1)

    # `default` is the key `xcli init` scaffolds — but a hand-built project
    # (or one predating xcli init) may name its only database something else
    # entirely (e.g. `db`). Unambiguous in that single-entry case; only an
    # actual error when there's more than one and none is named `default`.
    entry = databases.get("default")
    if entry is None:
        if len(databases) == 1:
            entry = next(iter(databases.values()))
        else:
            keys = ", ".join(databases.keys())
            console.print(
                f"[red]No services.databases.default entry, and multiple databases "
                f"configured ({keys}) — ambiguous which one to use for migrations.[/red]"
            )
            raise SystemExit(1)

    url = entry.get("url")
    if not url:
        console.print("[red]No 'url' on the resolved database entry in integration.yaml[/red]")
        raise SystemExit(1)

    expanded = os.path.expandvars(str(url))
    if "$" in expanded:
        # expandvars() leaves $VAR/${VAR} untouched when the env var isn't
        # set — surface that clearly instead of handing alembic a literal
        # "${DATABASE_URL}" string and letting it fail with a confusing
        # SQLAlchemy dialect error two layers down.
        dotenv_hint = cfg.get("app", {}).get("dotenv")
        where = f"app.dotenv ({dotenv_hint})" if dotenv_hint else "that the env var is set"
        console.print(
            f"[yellow]⚠[/yellow] Database URL still contains an unresolved variable: "
            f"[dim]{expanded}[/dim] — check {where}."
        )
    return expanded


def get_scan_paths() -> list[Path]:
    """Return paths to scan for SQLAlchemy models.

    Priority:
    1. migration.scan_paths in integration.yaml
    2. plugins directory
    3. project root (fallback)
    """
    cfg = load_config()
    raw_paths = cfg.get("migration", {}).get("scan_paths", [])
    root = project_root()

    if raw_paths:
        paths = []
        for raw in raw_paths:
            p = Path(raw)
            if not p.is_absolute():
                p = root / p
            if p.exists():
                paths.append(p.resolve())
            else:
                console.print(f"[yellow]⚠[/yellow] scan_path not found, skipping: [dim]{p}[/dim]")
        return paths

    # Default: plugins dir + project root
    candidates = [plugins_root(), root]
    return [p for p in candidates if p.exists()]


def get_backup_dir() -> Path:
    cfg = load_config()
    raw = cfg.get("migration", {}).get("backup_dir", "./backups/db")
    p = Path(raw)
    if not p.is_absolute():
        p = project_root() / p
    return p.resolve()


def create_alembic_config(directory: str = "alembic") -> Config:
    root = project_root()
    alembic_dir = root / directory
    cfg = Config()
    cfg.set_main_option("script_location", str(alembic_dir))
    cfg.set_main_option("sqlalchemy.url", get_database_url())
    cfg.config_file_name = str(root / "alembic.ini")
    return cfg


def run_alembic_command(directory: str, action) -> None:
    """Runs `action(cfg)` against the resolved alembic Config for `directory`
    — transparently bridging to an async engine first when the project's
    database URL uses an async driver (e.g. `sqlite+aiosqlite`,
    `postgresql+asyncpg`, the norm for an xcore project — see CLAUDE.md
    "Async everywhere").

    Every xcore-generated migrations/env.py (see app/marketplace/migrations/
    env.py and its siblings) already supports this: its run_migrations_online()
    checks `context.config.attributes.get("connection")` first and only falls
    back to a plain `engine_from_config(...).connect()` when none was
    supplied — that fallback synchronously drives whatever DBAPI the URL
    names, which fails immediately on an async one ("MissingGreenlet:
    greenlet_spawn has not been called"). Supplying the connection ourselves,
    exactly like xcore.services.database.migrations.MigrationRunner already
    does for plugins loaded by the framework itself, is what makes both paths
    actually work — this was previously sync-only and broke on any real
    xcore project's database."""
    from sqlalchemy.engine import make_url

    url = get_database_url()
    try:
        is_async = make_url(url).get_dialect().is_async
    except Exception:
        is_async = False

    if not is_async:
        action(create_alembic_config(directory))
        return

    try:
        from sqlalchemy.ext.asyncio import create_async_engine
    except ImportError:
        console.print(
            "[red]Async database URL but SQLAlchemy's async extras aren't installed.[/red]"
        )
        raise SystemExit(1)

    import asyncio

    async def _run() -> None:
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:

                def _do(sync_conn):
                    cfg = create_alembic_config(directory)
                    cfg.attributes["connection"] = sync_conn
                    action(cfg)

                await conn.run_sync(_do)
        finally:
            await engine.dispose()

    asyncio.run(_run())


# ── Model discovery ────────────────────────────────────────────

def discover_models(paths: list[Path] | None = None) -> DiscoveryResult:
    """Scan paths for SQLAlchemy DeclarativeBase subclasses and MetaData objects."""
    scan_paths = paths if paths is not None else get_scan_paths()

    metadata_by_id: dict[int, MetaData] = {}
    loaded_modules: list[str] = []
    warnings: list[str] = []
    model_count = 0

    for scan_root in scan_paths:
        if not scan_root.exists():
            warnings.append(f"Path not found: {scan_root}")
            continue

        for py_file in _iter_python_files(scan_root):
            try:
                module = _load_module(py_file, scan_root)
            except Exception as exc:
                warnings.append(f"{py_file}: {exc}")
                continue

            rel = str(py_file.relative_to(project_root()))
            loaded_modules.append(rel)
            for metadata in _extract_metadata(module):
                if id(metadata) not in metadata_by_id:
                    metadata_by_id[id(metadata)] = metadata
                    model_count += len(metadata.tables)

    return DiscoveryResult(
        target_metadata=list(metadata_by_id.values()),
        modules=loaded_modules,
        warnings=warnings,
        model_count=model_count,
    )


def render_discovery_summary(result: DiscoveryResult) -> str:
    return (
        f"modules={len(result.modules)}, "
        f"metadata_groups={len(result.target_metadata)}, "
        f"tables≈{result.model_count}, "
        f"warnings={len(result.warnings)}"
    )


# ── DB URL parsing ─────────────────────────────────────────────

def parse_db_url(url: str) -> DBInfo:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()

    # Normalize dialect
    if "sqlite" in scheme:
        dialect = "sqlite"
    elif "postgresql" in scheme or "postgres" in scheme:
        dialect = "postgresql"
    elif "mariadb" in scheme:
        dialect = "mariadb"
    elif "mysql" in scheme:
        dialect = "mysql"
    else:
        dialect = scheme.split("+")[0]

    driver = scheme.split("+")[1] if "+" in scheme else ""

    # SQLite path: sqlite:///path or sqlite:////abs/path
    if dialect == "sqlite":
        db_path = parsed.path.lstrip("/")
        if url.startswith("sqlite:////"):
            db_path = "/" + db_path
        return DBInfo(
            dialect=dialect, driver=driver,
            host="", port=0, user="", password="",
            database=db_path, url=url,
        )

    return DBInfo(
        dialect=dialect,
        driver=driver,
        host=parsed.hostname or "localhost",
        port=parsed.port or _default_port(dialect),
        user=parsed.username or "",
        password=parsed.password or "",
        database=(parsed.path or "").lstrip("/"),
        url=url,
    )


def _default_port(dialect: str) -> int:
    return {"postgresql": 5432, "mysql": 3306, "mariadb": 3306}.get(dialect, 0)


# ── Backup ─────────────────────────────────────────────────────

def backup_database(url: str | None = None, backup_dir: Path | None = None) -> BackupResult:
    """Create a timestamped backup of the database."""
    db_url = url or get_database_url()
    dest_dir = backup_dir or get_backup_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)

    info = parse_db_url(db_url)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if info.dialect == "sqlite":
        return _backup_sqlite(info, dest_dir, ts)
    elif info.dialect == "postgresql":
        return _backup_postgres(info, dest_dir, ts)
    elif info.dialect in ("mysql", "mariadb"):
        return _backup_mysql(info, dest_dir, ts)
    else:
        raise ValueError(f"Unsupported dialect for backup: {info.dialect}")


def _backup_sqlite(info: DBInfo, dest_dir: Path, ts: str) -> BackupResult:
    import sqlite3

    src = Path(info.database)
    if not src.is_absolute():
        src = project_root() / src

    if not src.exists():
        raise FileNotFoundError(f"SQLite database not found: {src}")

    backup_path = dest_dir / f"backup_{ts}_{src.stem}.sqlite3"

    # Use SQLite online backup API (safe even with active connections)
    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(backup_path))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    return BackupResult(path=backup_path, dialect="sqlite", size_bytes=backup_path.stat().st_size)


def _backup_postgres(info: DBInfo, dest_dir: Path, ts: str) -> BackupResult:
    backup_path = dest_dir / f"backup_{ts}_{info.database}.sql"

    cmd = ["pg_dump", "-h", info.host, "-p", str(info.port)]
    if info.user:
        cmd += ["-U", info.user]
    cmd += ["-Fp", "-f", str(backup_path), info.database]

    env = _pg_env(info)
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {result.stderr.strip()}")

    return BackupResult(path=backup_path, dialect="postgresql", size_bytes=backup_path.stat().st_size)


def _backup_mysql(info: DBInfo, dest_dir: Path, ts: str) -> BackupResult:
    backup_path = dest_dir / f"backup_{ts}_{info.database}.sql"

    cmd = [
        "mysqldump",
        f"-h{info.host}", f"-P{info.port}",
        f"-u{info.user}",
        f"--password={info.password}",
        "--single-transaction",
        "--routines",
        "--triggers",
        info.database,
    ]

    with open(backup_path, "w", encoding="utf-8") as f:
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0:
        backup_path.unlink(missing_ok=True)
        raise RuntimeError(f"mysqldump failed: {result.stderr.strip()}")

    return BackupResult(path=backup_path, dialect=info.dialect, size_bytes=backup_path.stat().st_size)


# ── Restore ────────────────────────────────────────────────────

def restore_database(backup_path: Path, url: str | None = None) -> None:
    """Restore a database from a backup file."""
    db_url = url or get_database_url()
    info = parse_db_url(db_url)

    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")

    if info.dialect == "sqlite":
        _restore_sqlite(info, backup_path)
    elif info.dialect == "postgresql":
        _restore_postgres(info, backup_path)
    elif info.dialect in ("mysql", "mariadb"):
        _restore_mysql(info, backup_path)
    else:
        raise ValueError(f"Unsupported dialect for restore: {info.dialect}")


def _restore_sqlite(info: DBInfo, backup_path: Path) -> None:
    import sqlite3

    dest = Path(info.database)
    if not dest.is_absolute():
        dest = project_root() / dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(str(backup_path))
    dst_conn = sqlite3.connect(str(dest))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()


def _restore_postgres(info: DBInfo, backup_path: Path) -> None:
    cmd = ["psql", "-h", info.host, "-p", str(info.port)]
    if info.user:
        cmd += ["-U", info.user]
    cmd += ["-d", info.database, "-f", str(backup_path)]

    result = subprocess.run(cmd, env=_pg_env(info), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"psql restore failed: {result.stderr.strip()}")


def _restore_mysql(info: DBInfo, backup_path: Path) -> None:
    cmd = [
        "mysql",
        f"-h{info.host}", f"-P{info.port}",
        f"-u{info.user}",
        f"--password={info.password}",
        info.database,
    ]
    with open(backup_path, encoding="utf-8") as f:
        result = subprocess.run(cmd, stdin=f, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"mysql restore failed: {result.stderr.strip()}")


# ── Helpers ────────────────────────────────────────────────────

def _pg_env(info: DBInfo) -> dict:
    import os
    env = os.environ.copy()
    if info.password:
        env["PGPASSWORD"] = info.password
    return env


def list_backups(backup_dir: Path | None = None) -> list[Path]:
    dest_dir = backup_dir or get_backup_dir()
    if not dest_dir.exists():
        return []
    exts = {".sqlite3", ".sql", ".dump"}
    return sorted(
        (p for p in dest_dir.iterdir() if p.is_file() and p.suffix in exts),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _iter_python_files(scan_root: Path) -> Iterator[Path]:
    for path in scan_root.rglob("*.py"):
        if any(part in _IGNORED_PARTS for part in path.parts):
            continue
        yield path


@contextmanager
def _sys_path(*paths: Path) -> Iterator[None]:
    original = list(sys.path)
    inserts = [str(p.resolve()) for p in paths if p.exists()]
    for entry in reversed(inserts):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    try:
        yield
    finally:
        sys.path[:] = original


def _load_module(py_file: Path, scan_root: Path) -> ModuleType:
    module_name = "xcli_scan_" + "_".join(py_file.with_suffix("").parts[-4:])
    spec = importlib.util.spec_from_file_location(module_name, py_file)
    if spec is None or spec.loader is None:
        raise ImportError("unable to build module spec")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        with _sys_path(project_root(), scan_root, scan_root / "src"):
            spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def _extract_metadata(module: ModuleType) -> list[MetaData]:
    found: dict[int, MetaData] = {}
    for obj in vars(module).values():
        metadata = _metadata_from_object(obj)
        if metadata is not None:
            found.setdefault(id(metadata), metadata)
    return list(found.values())


def _metadata_from_object(obj: object) -> MetaData | None:
    if isinstance(obj, MetaData):
        return obj

    if inspect.isclass(obj):
        if obj is not DeclarativeBase and issubclass(obj, DeclarativeBase):
            return getattr(obj, "metadata", None)
        metadata = getattr(obj, "metadata", None)
        registry = getattr(obj, "registry", None)
        if isinstance(metadata, MetaData) and registry is not None:
            return metadata

    metadata = getattr(obj, "metadata", None)
    if isinstance(metadata, MetaData) and getattr(obj, "__table__", None) is not None:
        return metadata

    return None
