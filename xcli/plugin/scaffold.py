from pathlib import Path

import yaml

# ── Templates src/main.py ─────────────────────────────────────

_TRUSTED_TEMPLATE = '''\
from xcore.kernel.api.contract import TrustedBase, error, ok


class Plugin(TrustedBase):
    """
    {description}
    Execution mode : trusted — full service injection via self.get_service().
    """

    async def on_load(self) -> None:
        # Access services here, e.g.:
        #   self.db    = self.get_service("db")
        #   self.cache = self.get_service("cache")
        pass

    async def on_reload(self) -> None:
        pass

    async def on_unload(self) -> None:
        pass

    async def handle(self, action: str, payload: dict) -> dict:
        match action:
            case "ping":
                return ok(message="pong")
            case _:
                return error(f"unknown action: {{action!r}}")

    def get_router(self):
        """Expose custom HTTP routes under /plugin/{name}/."""
        from fastapi import APIRouter

        router = APIRouter(prefix="/", tags=["{name}"])

        @router.get("/")
        async def index():
            return {{"plugin": "{name}", "status": "ok"}}

        return router
'''

_SANDBOXED_TEMPLATE = '''\
from xcore.kernel.api.contract import error, ok


class Plugin:
    """
    {description}
    Execution mode : sandboxed — runs in an isolated subprocess.
    No direct service injection; use IPC if needed.
    """

    _config: dict = {{}}

    async def handle(self, action: str, payload: dict) -> dict:
        match action:
            case "ping":
                return ok(message="pong")
            case _:
                return error(f"unknown action: {{action!r}}")
'''

_LEGACY_TEMPLATE = '''\
from xcore.kernel.api.contract import error, ok


class Plugin:
    """
    {description}
    Execution mode : legacy — duck-typed, minimal lifecycle hooks.
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
                return ok(message="pong")
            case _:
                return error(f"unknown action: {{action!r}}")
'''

_TEMPLATES = {
    "trusted": _TRUSTED_TEMPLATE,
    "sandboxed": _SANDBOXED_TEMPLATE,
    "legacy": _LEGACY_TEMPLATE,
}


# ── Manifest builder ──────────────────────────────────────────

def _build_manifest(cfg: dict) -> dict:
    manifest: dict = {
        "name": cfg["name"],
        "version": cfg["version"],
        "author": cfg["author"],
        "description": cfg["description"],
        "framework_version": cfg["framework_version"],
        "execution_mode": cfg["execution_mode"],
        "entry_point": cfg["entry_point"],
    }

    if cfg.get("allowed_imports"):
        manifest["allowed_imports"] = cfg["allowed_imports"]

    if cfg.get("requires"):
        manifest["requires"] = cfg["requires"]

    if cfg.get("env"):
        manifest["env"] = cfg["env"]
        manifest["envconfiguration"] = {"inject": True, "env_file": ".env"}

    resources: dict = {}
    if cfg.get("timeout_seconds", 10) != 10:
        resources["timeout_seconds"] = cfg["timeout_seconds"]
    if cfg.get("max_memory_mb", 128) != 128:
        resources["max_memory_mb"] = cfg["max_memory_mb"]
    if cfg.get("max_disk_mb", 50) != 50:
        resources["max_disk_mb"] = cfg["max_disk_mb"]
    rl_calls = cfg.get("rate_limit_calls", 100)
    rl_period = cfg.get("rate_limit_period", 60)
    if rl_calls != 100 or rl_period != 60:
        resources["rate_limit"] = {"calls": rl_calls, "period_seconds": rl_period}
    if resources:
        manifest["resources"] = resources

    runtime: dict = {}
    if not cfg.get("healthcheck_enabled", True):
        runtime["health_check"] = {"enabled": False}
    if cfg.get("retry_attempts", 1) > 1:
        runtime.setdefault("retry", {})["max_attempts"] = cfg["retry_attempts"]
    if runtime:
        manifest["runtime"] = runtime

    allowed_paths = cfg.get("filesystem_allowed", ["data/"])
    denied_paths = cfg.get("filesystem_denied", ["src/"])
    if allowed_paths != ["data/"] or denied_paths != ["src/"]:
        manifest["filesystem"] = {
            "allowed_paths": allowed_paths,
            "denied_paths": denied_paths,
        }

    if cfg.get("permissions"):
        manifest["permissions"] = cfg["permissions"]

    return manifest


# ── File writer ───────────────────────────────────────────────

def scaffold(cfg: dict, target_dir: Path) -> list[Path]:
    """Generate the plugin directory structure and return created paths."""
    cfg = {
        "version": "0.1.0",
        "author": "unknown",
        "description": "",
        "framework_version": ">=2.0",
        "entry_point": "src/main.py",
        "allowed_imports": [],
        "requires": [],
        "env": {},
        "permissions": [],
        **cfg,
    }
    created: list[Path] = []

    def write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(path)

    # plugin.yaml
    manifest = _build_manifest(cfg)
    write(
        target_dir / "plugin.yaml",
        yaml.dump(manifest, default_flow_style=False, allow_unicode=True, sort_keys=False),
    )

    # src/__init__.py
    write(target_dir / "src" / "__init__.py", "")

    # src/main.py
    template = _TEMPLATES[cfg["execution_mode"]]
    write(
        target_dir / "src" / "main.py",
        template.format(name=cfg["name"], description=cfg["description"] or ""),
    )

    # data/.gitkeep
    write(target_dir / "data" / ".gitkeep", "")

    # .env (only if env vars defined)
    if cfg.get("env"):
        env_lines = "\n".join(f'{k}={v}' for k, v in cfg["env"].items())
        write(target_dir / ".env", env_lines + "\n")

    return created
