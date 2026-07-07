"""
config.py — Parsing et validation de xcore-deploy.yaml.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_ENV_RE = re.compile(r"\$\{([^}]+)\}")


def _interpolate(value: str) -> str:
    """Remplace ${VAR} par la valeur de l'env système."""
    def _replace(m: re.Match) -> str:
        key = m.group(1)
        val = os.environ.get(key)
        if val is None:
            raise ValueError(f"Variable d'environnement manquante : ${{{key}}}")
        return val
    return _ENV_RE.sub(_replace, value)


@dataclass
class Hook:
    cmd: str                   # commande shell à exécuter
    cwd: str | None = None     # répertoire d'exécution (défaut : répertoire du projet)
    ignore_errors: bool = False  # si True, continue même en cas d'erreur

    @classmethod
    def from_dict(cls, d: dict) -> "Hook":
        if isinstance(d, str):
            return cls(cmd=d)
        return cls(
            cmd=d["cmd"],
            cwd=d.get("cwd"),
            ignore_errors=d.get("ignore_errors", False),
        )


@dataclass
class PluginHooks:
    pre_deploy: list[Hook] = field(default_factory=list)
    post_deploy: list[Hook] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict | None) -> "PluginHooks":
        if not d:
            return cls()
        return cls(
            pre_deploy=[Hook.from_dict(h) for h in d.get("pre_deploy", [])],
            post_deploy=[Hook.from_dict(h) for h in d.get("post_deploy", [])],
        )


@dataclass
class PluginEntry:
    name: str
    source: str                # chemin local vers le dossier du plugin
    sign: bool = False         # signer avant transfert
    reload: bool = True        # hot-reload après transfert
    only: list[str] = field(default_factory=list)  # targets autorisés (vide = tous)
    hooks: PluginHooks = field(default_factory=PluginHooks)

    @classmethod
    def from_dict(cls, d: dict) -> "PluginEntry":
        return cls(
            name=d["name"],
            source=d["source"],
            sign=d.get("sign", False),
            reload=d.get("reload", True),
            only=d.get("only", []),
            hooks=PluginHooks.from_dict(d.get("hooks")),
        )


@dataclass
class Target:
    name: str
    host: str
    user: str
    plugins_root: str          # chemin absolu sur le serveur distant
    port: int = 22
    ssh_key: str | None = None
    password: str | None = None
    xcore_url: str | None = None
    xcore_token: str | None = None

    @classmethod
    def from_dict(cls, name: str, d: dict) -> "Target":
        return cls(
            name=name,
            host=_interpolate(d["host"]),
            user=d["user"],
            plugins_root=d["plugins_root"],
            port=d.get("port", 22),
            ssh_key=d.get("ssh_key"),
            password=_interpolate(d["password"]) if d.get("password") else None,
            xcore_url=_interpolate(d["xcore_url"]) if d.get("xcore_url") else None,
            xcore_token=_interpolate(d["xcore_token"]) if d.get("xcore_token") else None,
        )


@dataclass
class GlobalHooks:
    pre_deploy: list[Hook] = field(default_factory=list)
    post_deploy: list[Hook] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict | None) -> "GlobalHooks":
        if not d:
            return cls()
        return cls(
            pre_deploy=[Hook.from_dict(h) for h in d.get("pre_deploy", [])],
            post_deploy=[Hook.from_dict(h) for h in d.get("post_deploy", [])],
        )


@dataclass
class DeployConfig:
    targets: dict[str, Target]
    plugins: list[PluginEntry]
    hooks: GlobalHooks

    @classmethod
    def load(cls, path: Path) -> "DeployConfig":
        if not path.exists():
            raise FileNotFoundError(
                f"Fichier de déploiement introuvable : {path}\n"
                f"Crée-le avec : xcli deploy init"
            )
        raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

        targets = {
            name: Target.from_dict(name, cfg)
            for name, cfg in raw.get("targets", {}).items()
        }
        if not targets:
            raise ValueError("Aucun target défini dans xcore-deploy.yaml")

        plugins = [PluginEntry.from_dict(p) for p in raw.get("plugins", [])]

        return cls(
            targets=targets,
            plugins=plugins,
            hooks=GlobalHooks.from_dict(raw.get("hooks")),
        )

    def get_target(self, name: str) -> Target:
        if name not in self.targets:
            available = ", ".join(self.targets)
            raise KeyError(f"Target '{name}' introuvable. Disponibles : {available}")
        return self.targets[name]

    def plugins_for_target(self, target_name: str) -> list[PluginEntry]:
        return [
            p for p in self.plugins
            if not p.only or target_name in p.only
        ]
