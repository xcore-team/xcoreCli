from __future__ import annotations

import importlib.util
import inspect
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Iterator

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
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "data",
    "alembic",
    "migrations",
}


@dataclass(slots=True)
class DiscoveryResult:
    target_metadata: list[MetaData]
    modules: list[str]
    warnings: list[str]


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


def get_database_url() -> str:
    cfg = load_config()
    databases = cfg.get("services", {}).get("databases", {})
    default = databases.get("default", {})
    url = default.get("url")
    if not url:
        console.print(
            "[red]No database URL found in services.databases.default.url inside integration.yaml[/red]"
        )
        raise SystemExit(1)
    return str(url)


def create_alembic_config(directory: str = "alembic") -> Config:
    root = project_root()
    alembic_dir = root / directory
    cfg = Config()
    cfg.set_main_option("script_location", str(alembic_dir))
    cfg.set_main_option("sqlalchemy.url", get_database_url())
    cfg.config_file_name = str(root / "alembic.ini")
    return cfg


def discover_models() -> DiscoveryResult:
    root = plugins_root()
    if not root.exists():
        console.print(f"[red]Plugins directory not found: [cyan]{root}[/cyan][/red]")
        raise SystemExit(1)

    metadata_by_id: dict[int, MetaData] = {}
    loaded_modules: list[str] = []
    warnings: list[str] = []

    for plugin_dir in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith('.')):
        for py_file in _iter_python_files(plugin_dir):
            try:
                module = _load_module(py_file, plugin_dir)
            except Exception as exc:
                warnings.append(f"{py_file}: {exc}")
                continue

            loaded_modules.append(str(py_file.relative_to(project_root())))
            for metadata in _extract_metadata(module):
                metadata_by_id.setdefault(id(metadata), metadata)

    return DiscoveryResult(
        target_metadata=list(metadata_by_id.values()),
        modules=loaded_modules,
        warnings=warnings,
    )


def render_discovery_summary(result: DiscoveryResult) -> str:
    parts = [
        f"loaded={len(result.modules)} module(s)",
        f"metadata={len(result.target_metadata)}",
        f"warnings={len(result.warnings)}",
    ]
    return ", ".join(parts)


def _iter_python_files(plugin_dir: Path) -> Iterator[Path]:
    for path in plugin_dir.rglob("*.py"):
        if any(part in _IGNORED_PARTS for part in path.parts):
            continue
        yield path


@contextmanager
def _sys_path(*paths: Path) -> Iterator[None]:
    original = list(sys.path)
    inserts = [str(path.resolve()) for path in paths if path.exists()]
    for entry in reversed(inserts):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    try:
        yield
    finally:
        sys.path[:] = original


def _load_module(py_file: Path, plugin_dir: Path) -> ModuleType:
    module_name = "xcli_migrations_" + "_".join(py_file.with_suffix("").parts)
    spec = importlib.util.spec_from_file_location(module_name, py_file)
    if spec is None or spec.loader is None:
        raise ImportError("unable to build module spec")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        with _sys_path(project_root(), plugin_dir, plugin_dir / "src"):
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
