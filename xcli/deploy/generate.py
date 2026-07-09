from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def scan_plugins(project_root: Path, plugins_dir: str) -> list[dict[str, Any]]:
    plugins_path = (project_root / plugins_dir).resolve()
    if not plugins_path.exists():
        return []

    result = []
    for item in sorted(plugins_path.iterdir()):
        if not item.is_dir() or item.name.startswith("_"):
            continue
        plugin_yaml = item / "plugin.yaml"
        if not plugin_yaml.exists():
            continue

        entry = {"name": item.name, "source": f"{plugins_dir}/{item.name}", "sign": True, "reload": True}
        result.append(entry)
    return result


def scan_extensions(project_root: Path, extensions_dir: str) -> list[dict[str, Any]]:
    ext_path = (project_root / extensions_dir).resolve()
    if not ext_path.exists():
        return []

    result = []
    for item in sorted(ext_path.iterdir()):
        if not item.is_dir() or item.name.startswith("_"):
            continue
        init_file = item / "__init__.py"
        if not init_file.exists():
            continue

        entry = {"name": item.name, "source": f"{extensions_dir}/{item.name}", "restart": True}
        result.append(entry)
    return result


def has_integration_yaml(project_root: Path) -> bool:
    return (project_root / "integration.yaml").exists()


def load_existing(file_path: Path) -> dict[str, Any]:
    if not file_path.exists():
        return {}
    raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    return raw or {}


def generate_config(
    project_root: Path,
    plugins_dir: str = "./app",
    extensions_dir: str = "./extensions",
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing = existing or {}

    plugins = scan_plugins(project_root, plugins_dir.lstrip("./"))
    extensions = scan_extensions(project_root, extensions_dir.lstrip("./"))
    has_integration = has_integration_yaml(project_root)

    config: dict[str, Any] = {"version": "1"}

    targets = existing.get("targets")
    if targets:
        config["targets"] = targets
    else:
        config["targets"] = {
            "production": {
                "host": "${PROD_HOST}",
                "port": 22,
                "user": "deploy",
                "ssh_key": "~/.ssh/id_ed25519",
                "xcore_url": "${PROD_XCORE_URL}",
                "xcore_token": "${PROD_XCORE_ADMIN_TOKEN}",
                "plugins_root": "/opt/xcore/app/plugins",
                "extensions_root": "/opt/xcore/app/extensions",
            },
            "staging": {
                "host": "${STAGING_HOST}",
                "port": 22,
                "user": "deploy",
                "ssh_key": "~/.ssh/id_ed25519",
                "xcore_url": "${STAGING_XCORE_URL}",
                "xcore_token": "${STAGING_XCORE_ADMIN_TOKEN}",
                "plugins_root": "/opt/xcore/app/plugins",
                "extensions_root": "/opt/xcore/app/extensions",
            },
        }

    hooks = existing.get("hooks")
    if hooks:
        config["hooks"] = hooks

    if has_integration:
        existing_integration = existing.get("integration")
        if existing_integration:
            config["integration"] = existing_integration
        else:
            config["integration"] = {
                "source": "./integration.yaml",
                "remote_path": "/opt/xcore/integration.yaml",
                "restart_xcore": True,
            }

    if extensions:
        config["extensions"] = extensions

    if plugins:
        config["plugins"] = plugins

    return config


def format_config(config: dict[str, Any]) -> str:
    return yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)
