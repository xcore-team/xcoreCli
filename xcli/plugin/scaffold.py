from __future__ import annotations

from pathlib import Path

import yaml

# ── src/main.py templates ─────────────────────────────────────

_TRUSTED_MAIN = '''\
from xcore.kernel.api.contract import TrustedBase, error, ok


class Plugin(TrustedBase):
    """{description}"""

    async def on_load(self) -> None:
        """Appelé au chargement — récupérer les services ici."""{db_on_load}{cache_on_load}
        pass

    async def on_start(self) -> None:
        """Appelé au démarrage — lancer les jobs planifiés ici."""{scheduler_on_start}
        pass

    async def on_reload(self) -> None:
        pass

    async def on_unload(self) -> None:
        pass

    async def handle(self, action: str, payload: dict) -> dict:
        match action:
            case "ping":
                return ok(message="pong", plugin="{name}")
            case _:
                return error(f"Action inconnue: {{action!r}}")

    def get_router(self):{router_body}
'''

_SANDBOXED_MAIN = '''\
from xcore.kernel.api.contract import error, ok


class Plugin:
    """{description}
    Mode sandboxé — s\'exécute dans un sous-processus isolé.
    Pas d\'injection de service directe ; utiliser IPC si nécessaire.
    """

    _config: dict = {{}}

    async def handle(self, action: str, payload: dict) -> dict:
        match action:
            case "ping":
                return ok(message="pong", plugin="{name}")
            case _:
                return error(f"Action inconnue: {{action!r}}")
'''

_LEGACY_MAIN = '''\
from xcore.kernel.api.contract import error, ok


class Plugin:
    """{description}
    Mode legacy — duck-typed, hooks minimaux.
    """

    _config: dict = {{}}

    async def on_init(self) -> None:
        pass

    async def on_start(self) -> None:
        pass

    async def on_stop(self) -> None:
        pass

    async def handle(self, action: str, payload: dict) -> dict:
        match action:
            case "ping":
                return ok(message="pong", plugin="{name}")
            case _:
                return error(f"Action inconnue: {{action!r}}")
'''

# ── models.py template ────────────────────────────────────────

_MODELS_PY = '''\
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class {class_name}(Base):
    __tablename__ = "{table_name}"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<{class_name} id={{self.id}} name={{self.name!r}}>"
'''

# ── schemas.py template ───────────────────────────────────────

_SCHEMAS_PY = '''\
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class {class_name}Base(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class {class_name}Create({class_name}Base):
    pass


class {class_name}Update(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)


class {class_name}Response({class_name}Base):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
'''

# ── tests/test_plugin.py template ────────────────────────────

_TEST_PY = '''\
import pytest


@pytest.mark.asyncio
async def test_ping():
    from src.main import Plugin
    plugin = Plugin()
    result = await plugin.handle("ping", {{}})
    assert result["success"] is True
    assert result["data"]["message"] == "pong"


@pytest.mark.asyncio
async def test_unknown_action():
    from src.main import Plugin
    plugin = Plugin()
    result = await plugin.handle("nonexistent", {{}})
    assert result["success"] is False
'''

# ── Router snippets ───────────────────────────────────────────

_ROUTER_WITH_ROUTES = """\

        from fastapi import APIRouter

        router = APIRouter(prefix="/{name}", tags=["{name}"])

        @router.get("/")
        async def index():
            return {{"plugin": "{name}", "status": "ok"}}

        return router"""

_ROUTER_STUB = """\

        from fastapi import APIRouter
        return APIRouter(prefix="/{name}", tags=["{name}"])"""

# ── on_load snippets ──────────────────────────────────────────

_DB_ON_LOAD = "\n        self.db    = self.get_service('db')"
_CACHE_ON_LOAD = "\n        self.cache = self.get_service('cache')"
_SCHEDULER_ON_START = """
        # Exemple : job planifié toutes les heures
        # @self.scheduler.interval(hours=1)
        # async def _sync():
        #     pass"""


# ── Manifest builder ──────────────────────────────────────────

def _build_manifest(cfg: dict) -> dict:
    manifest: dict = {
        "name":              cfg["name"],
        "version":           cfg.get("version", "0.1.0"),
        "author":            cfg.get("author", ""),
        "description":       cfg.get("description", ""),
        "framework_version": cfg.get("framework_version", ">=2.0"),
        "execution_mode":    cfg["execution_mode"],
        "entry_point":       cfg.get("entry_point", "src/main.py"),
    }

    # allowed_imports — only for sandboxed
    if cfg["execution_mode"] == "sandboxed" and cfg.get("allowed_imports"):
        manifest["allowed_imports"] = cfg["allowed_imports"]

    # permissions — database, cache, scheduler
    permissions = list(cfg.get("permissions", []))
    if cfg.get("has_db"):
        permissions.append({"resource": "database", "actions": ["read", "write"]})
    if cfg.get("has_cache"):
        permissions.append({"resource": "cache", "actions": ["read", "write"]})
    if cfg.get("has_scheduler"):
        permissions.append({"resource": "scheduler", "actions": ["schedule"]})
    if permissions:
        manifest["permissions"] = permissions

    # resources
    resources: dict = {}
    timeout    = cfg.get("timeout_seconds", 30)
    max_mem    = cfg.get("max_memory_mb", 256)
    max_disk   = cfg.get("max_disk_mb", 100)
    rl_calls   = cfg.get("rate_limit_calls", 100)
    rl_period  = cfg.get("rate_limit_period", 60)

    if cfg["execution_mode"] == "sandboxed":
        resources = {
            "timeout_seconds": timeout,
            "max_memory_mb":   max_mem,
            "max_disk_mb":     max_disk,
            "rate_limit":      {"calls": rl_calls, "period_seconds": rl_period},
        }
    else:
        if timeout != 30:
            resources["timeout_seconds"] = timeout
        if rl_calls != 100 or rl_period != 60:
            resources["rate_limit"] = {"calls": rl_calls, "period_seconds": rl_period}

    if resources:
        manifest["resources"] = resources

    # filesystem (sandboxed)
    if cfg["execution_mode"] == "sandboxed":
        manifest["filesystem"] = {
            "allowed_paths": cfg.get("filesystem_allowed", ["data/"]),
            "denied_paths":  cfg.get("filesystem_denied", ["src/"]),
        }

    # env vars
    if cfg.get("env"):
        manifest["env"] = cfg["env"]
        manifest["envconfiguration"] = {"inject": True, "env_file": ".env"}

    # requires (plugin deps)
    if cfg.get("requires"):
        manifest["requires"] = cfg["requires"]

    return manifest


# ── Main entry ────────────────────────────────────────────────

def scaffold(cfg: dict, target_dir: Path) -> list[Path]:
    """Generate a plugin directory and return created paths."""
    cfg = {
        "version":          "0.1.0",
        "author":           "",
        "description":      "",
        "framework_version":">=2.0",
        "entry_point":      "src/main.py",
        "allowed_imports":  [],
        "requires":         [],
        "env":              {},
        "permissions":      [],
        "has_db":           False,
        "has_cache":        False,
        "has_scheduler":    False,
        "has_routes":       True,
        **cfg,
    }

    created: list[Path] = []

    def write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(path)

    mode = cfg["execution_mode"]
    name = cfg["name"]
    class_name = "".join(w.capitalize() for w in name.split("_"))

    # ── plugin.yaml ───────────────────────────────────────────
    manifest = _build_manifest(cfg)
    write(
        target_dir / "plugin.yaml",
        yaml.dump(manifest, default_flow_style=False, allow_unicode=True, sort_keys=False),
    )

    # ── src/__init__.py ───────────────────────────────────────
    write(target_dir / "src" / "__init__.py", "")

    # ── src/main.py ───────────────────────────────────────────
    if mode == "trusted":
        router_body = _ROUTER_WITH_ROUTES if cfg["has_routes"] else _ROUTER_STUB
        main_content = _TRUSTED_MAIN.format(
            name=name,
            description=cfg["description"] or f"Plugin {name}",
            db_on_load=_DB_ON_LOAD if cfg["has_db"] else "",
            cache_on_load=_CACHE_ON_LOAD if cfg["has_cache"] else "",
            scheduler_on_start=_SCHEDULER_ON_START if cfg["has_scheduler"] else "",
            router_body=router_body.format(name=name),
        )
    elif mode == "sandboxed":
        main_content = _SANDBOXED_MAIN.format(
            name=name,
            description=cfg["description"] or f"Plugin {name}",
        )
    else:
        main_content = _LEGACY_MAIN.format(
            name=name,
            description=cfg["description"] or f"Plugin {name}",
        )

    write(target_dir / "src" / "main.py", main_content)

    # ── src/models.py (si has_db) ─────────────────────────────
    if cfg.get("has_db"):
        write(
            target_dir / "src" / "models.py",
            _MODELS_PY.format(
                class_name=class_name,
                table_name=name,
            ),
        )
        # ── src/schemas.py ────────────────────────────────────
        write(
            target_dir / "src" / "schemas.py",
            _SCHEMAS_PY.format(class_name=class_name),
        )

    # ── tests/ ────────────────────────────────────────────────
    write(target_dir / "tests" / "__init__.py", "")
    write(target_dir / "tests" / "test_plugin.py", _TEST_PY)

    # ── data/.gitkeep ─────────────────────────────────────────
    write(target_dir / "data" / ".gitkeep", "")

    # ── .env ──────────────────────────────────────────────────
    if cfg.get("env"):
        env_lines = "\n".join(f"{k}={v}" for k, v in cfg["env"].items())
        write(target_dir / ".env", env_lines + "\n")

    return created
