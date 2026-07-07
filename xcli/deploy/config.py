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
    cmd: str
    cwd: str | None = None
    ignore_errors: bool = False

    @classmethod
    def from_dict(cls, d: dict | str) -> "Hook":
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
class RepoSource:
    """Source GitHub/Git distante pour un plugin ou une extension."""
    url: str                        # https://github.com/org/repo ou git@github.com:org/repo
    ref: str = "main"               # branche, tag ou commit
    token: str | None = None        # token HTTPS pour repos privés (${GITHUB_TOKEN})
    subdirectory: str | None = None # sous-dossier dans le repo si le plugin n'est pas à la racine

    @classmethod
    def from_dict(cls, d: dict) -> "RepoSource":
        token_raw = d.get("token")
        return cls(
            url=d["repo"],
            ref=d.get("ref", "main"),
            token=_interpolate(token_raw) if token_raw else None,
            subdirectory=d.get("subdirectory"),
        )

    @property
    def is_ssh(self) -> bool:
        return self.url.startswith("git@")

    def authenticated_url(self) -> str:
        """URL HTTPS avec token intégré pour clone privé."""
        if self.token and not self.is_ssh:
            return self.url.replace("https://", f"https://{self.token}@", 1)
        return self.url


@dataclass
class PluginEntry:
    name: str
    source: str | None = None       # chemin local (mutuellement exclusif avec repo)
    repo: RepoSource | None = None  # source GitHub/Git
    sign: bool = False
    reload: bool = True
    only: list[str] = field(default_factory=list)
    hooks: PluginHooks = field(default_factory=PluginHooks)

    @classmethod
    def from_dict(cls, d: dict) -> "PluginEntry":
        if "repo" not in d and "source" not in d:
            raise ValueError(f"Plugin '{d.get('name')}' : 'source' ou 'repo' requis.")
        return cls(
            name=d["name"],
            source=d.get("source"),
            repo=RepoSource.from_dict(d) if "repo" in d else None,
            sign=d.get("sign", False),
            reload=d.get("reload", True),
            only=d.get("only", []),
            hooks=PluginHooks.from_dict(d.get("hooks")),
        )


@dataclass
class ExtensionEntry:
    """Service/extension XCore (déclaré sous services.extensions dans integration.yaml)."""
    name: str
    source: str | None = None
    repo: RepoSource | None = None
    restart: bool = True            # redémarrer le service après transfert via API
    only: list[str] = field(default_factory=list)
    hooks: PluginHooks = field(default_factory=PluginHooks)

    @classmethod
    def from_dict(cls, d: dict) -> "ExtensionEntry":
        if "repo" not in d and "source" not in d:
            raise ValueError(f"Extension '{d.get('name')}' : 'source' ou 'repo' requis.")
        return cls(
            name=d["name"],
            source=d.get("source"),
            repo=RepoSource.from_dict(d) if "repo" in d else None,
            restart=d.get("restart", True),
            only=d.get("only", []),
            hooks=PluginHooks.from_dict(d.get("hooks")),
        )


@dataclass
class IntegrationConfig:
    """Synchronisation de integration.yaml vers le(s) serveur(s) distant(s)."""
    source: str                    # chemin local du fichier
    remote_path: str = "/opt/xcore/integration.yaml"
    restart_xcore: bool = True     # redémarrer xcore après mise à jour
    only: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "IntegrationConfig":
        return cls(
            source=d["source"],
            remote_path=d.get("remote_path", "/opt/xcore/integration.yaml"),
            restart_xcore=d.get("restart_xcore", True),
            only=d.get("only", []),
        )


@dataclass
class Target:
    name: str
    host: str
    user: str
    plugins_root: str
    port: int = 22
    ssh_key: str | None = None
    password: str | None = None
    xcore_url: str | None = None
    xcore_token: str | None = None
    extensions_root: str | None = None  # chemin distant des extensions (défaut: ../extensions relatif à plugins_root)

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
            extensions_root=d.get("extensions_root"),
        )

    def resolved_extensions_root(self) -> str:
        if self.extensions_root:
            return self.extensions_root
        parent = str(Path(self.plugins_root).parent)
        return f"{parent}/extensions"


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
    extensions: list[ExtensionEntry]
    integration: IntegrationConfig | None
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
        extensions = [ExtensionEntry.from_dict(e) for e in raw.get("extensions", [])]
        integration = (
            IntegrationConfig.from_dict(raw["integration"])
            if raw.get("integration")
            else None
        )

        return cls(
            targets=targets,
            plugins=plugins,
            extensions=extensions,
            integration=integration,
            hooks=GlobalHooks.from_dict(raw.get("hooks")),
        )

    def get_target(self, name: str) -> Target:
        if name not in self.targets:
            available = ", ".join(self.targets)
            raise KeyError(f"Target '{name}' introuvable. Disponibles : {available}")
        return self.targets[name]

    def plugins_for_target(self, target_name: str) -> list[PluginEntry]:
        return [p for p in self.plugins if not p.only or target_name in p.only]

    def extensions_for_target(self, target_name: str) -> list[ExtensionEntry]:
        return [e for e in self.extensions if not e.only or target_name in e.only]

    def integration_for_target(self, target_name: str) -> IntegrationConfig | None:
        if not self.integration:
            return None
        if self.integration.only and target_name not in self.integration.only:
            return None
        return self.integration
