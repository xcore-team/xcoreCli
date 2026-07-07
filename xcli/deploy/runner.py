"""
runner.py — Exécution des hooks (pre/post) et orchestration du déploiement.
"""
from __future__ import annotations

import shlex
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.markup import escape
from rich.table import Table

if TYPE_CHECKING:
    from .config import DeployConfig, Hook, PluginEntry, Target

console = Console()

# Patterns à exclure de l'archive
_EXCLUDE = {
    "__pycache__", "*.pyc", "*.pyo", "*.pyd",
    ".git", ".venv", "venv", "node_modules",
    "*.egg-info", ".pytest_cache", ".mypy_cache",
    "dist", "build", ".DS_Store",
}


def _should_exclude(path: Path) -> bool:
    import fnmatch
    name = path.name
    for pat in _EXCLUDE:
        if fnmatch.fnmatch(name, pat):
            return True
    return False


# ── Hook Runner ───────────────────────────────────────────────────────────────


class HookRunner:
    def __init__(self, project_root: Path, dry_run: bool = False):
        self._root = project_root
        self._dry_run = dry_run

    def run_hooks(self, hooks: list["Hook"], label: str) -> bool:
        """Exécute une liste de hooks. Retourne False si une erreur bloquante survient."""
        if not hooks:
            return True

        console.print(f"\n  [bold dim]{label}[/bold dim]")
        for hook in hooks:
            ok = self._run_one(hook)
            if not ok and not hook.ignore_errors:
                return False
        return True

    def _run_one(self, hook: "Hook") -> bool:
        cwd = Path(hook.cwd).resolve() if hook.cwd else self._root
        cmd_display = escape(hook.cmd)

        if self._dry_run:
            console.print(f"    [dim]▷ (dry-run)[/dim] {cmd_display}")
            return True

        console.print(f"    [dim]▷[/dim] {cmd_display}")
        t0 = time.monotonic()

        try:
            result = subprocess.run(
                shlex.split(hook.cmd),
                cwd=cwd,
                capture_output=False,
                text=True,
            )
            elapsed = time.monotonic() - t0
            if result.returncode == 0:
                console.print(f"    [green]✓[/green] [dim]{elapsed:.1f}s[/dim]")
                return True
            else:
                console.print(
                    f"    [red]✗[/red] exit code {result.returncode} "
                    f"[dim]{elapsed:.1f}s[/dim]"
                )
                if hook.ignore_errors:
                    console.print("    [yellow]  (ignoré — ignore_errors: true)[/yellow]")
                return False
        except FileNotFoundError:
            console.print(f"    [red]✗[/red] commande introuvable : {cmd_display}")
            return False
        except Exception as e:
            console.print(f"    [red]✗[/red] erreur : {escape(str(e))}")
            return False


# ── Packager ─────────────────────────────────────────────────────────────────


def pack_plugin(plugin_path: Path, dest: Path) -> Path:
    """Crée une archive tar.gz du plugin dans dest/. Retourne le chemin de l'archive."""
    archive_path = dest / f"{plugin_path.name}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        for item in plugin_path.rglob("*"):
            if _should_exclude(item):
                continue
            arcname = item.relative_to(plugin_path.parent)
            tar.add(item, arcname=str(arcname))
    return archive_path


# ── Remote API ────────────────────────────────────────────────────────────────


def reload_plugin_remote(target: "Target", plugin_name: str) -> bool:
    """Appelle POST /plugins/{name}/reload sur l'instance XCore distante."""
    if not target.xcore_url:
        return True  # pas d'URL configurée, on skip silencieusement

    try:
        import httpx
    except ImportError:
        console.print("    [yellow]⚠ httpx non installé — reload API skippé[/yellow]")
        return True

    url = f"{target.xcore_url.rstrip('/')}/plugins/{plugin_name}/reload"
    headers = {}
    if target.xcore_token:
        headers["Authorization"] = f"Bearer {target.xcore_token}"

    try:
        resp = httpx.post(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            return True
        console.print(f"    [red]✗[/red] API reload HTTP {resp.status_code}: {escape(resp.text[:200])}")
        return False
    except Exception as e:
        console.print(f"    [red]✗[/red] API reload erreur : {escape(str(e))}")
        return False


# ── SSH Transport ─────────────────────────────────────────────────────────────


def _ssh_client(target: "Target"):
    try:
        import paramiko
    except ImportError:
        raise ImportError(
            "paramiko est requis pour le déploiement SSH.\n"
            "Installe-le : pip install paramiko"
        )

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs: dict = dict(
        hostname=target.host,
        port=target.port,
        username=target.user,
        timeout=30,
    )
    if target.ssh_key:
        key_path = Path(target.ssh_key).expanduser()
        connect_kwargs["key_filename"] = str(key_path)
    elif target.password:
        connect_kwargs["password"] = target.password

    client.connect(**connect_kwargs)
    return client


def transfer_plugin(target: "Target", archive: Path, plugin_name: str, dry_run: bool) -> bool:
    """Transfère l'archive sur le serveur et extrait le plugin."""
    remote_dir = f"{target.plugins_root}/{plugin_name}"
    remote_archive = f"/tmp/{archive.name}"

    if dry_run:
        console.print(f"    [dim]▷ (dry-run) sftp {archive.name} → {target.host}:{remote_dir}[/dim]")
        return True

    try:
        client = _ssh_client(target)
        sftp = client.open_sftp()

        # Crée le dossier distant si nécessaire
        stdin, stdout, stderr = client.exec_command(f"mkdir -p {remote_dir}")
        stdout.channel.recv_exit_status()

        # Transfert de l'archive
        sftp.put(str(archive), remote_archive)
        sftp.close()

        # Extraction sur le serveur
        cmd = f"tar -xzf {remote_archive} -C {target.plugins_root} && rm {remote_archive}"
        stdin, stdout, stderr = client.exec_command(cmd)
        exit_code = stdout.channel.recv_exit_status()
        client.close()

        if exit_code != 0:
            err = stderr.read().decode().strip()
            console.print(f"    [red]✗[/red] extraction échouée : {escape(err)}")
            return False
        return True

    except Exception as e:
        console.print(f"    [red]✗[/red] SSH erreur : {escape(str(e))}")
        return False


# ── Deploy Runner ─────────────────────────────────────────────────────────────


class DeployRunner:
    def __init__(
        self,
        config: "DeployConfig",
        target_name: str,
        project_root: Path,
        dry_run: bool = False,
        no_reload: bool = False,
        plugin_filter: str | None = None,
    ):
        self._cfg = config
        self._target = config.get_target(target_name)
        self._root = project_root
        self._dry_run = dry_run
        self._no_reload = no_reload
        self._plugin_filter = plugin_filter
        self._hooks = HookRunner(project_root, dry_run)

    def run(self) -> bool:
        target = self._target
        plugins = self._cfg.plugins_for_target(target.name)

        if self._plugin_filter:
            plugins = [p for p in plugins if p.name == self._plugin_filter]
            if not plugins:
                console.print(f"[red]Plugin '{self._plugin_filter}' introuvable dans la config.[/red]")
                return False

        console.print(
            f"\n[bold]Déploiement → [cyan]{target.name}[/cyan] "
            f"([dim]{target.user}@{target.host}[/dim])[/bold]"
        )
        if self._dry_run:
            console.print("[yellow]  Mode dry-run — aucune action réelle[/yellow]")

        # ── Hooks pre_deploy globaux ──────────────────────────────
        console.print("\n[bold dim]Hooks pre_deploy (global)[/bold dim]")
        if not self._hooks.run_hooks(self._cfg.hooks.pre_deploy, "pre_deploy global"):
            console.print("[red bold]✗ Hook pre_deploy global échoué — déploiement annulé.[/red bold]")
            return False

        # ── Déploiement plugin par plugin ─────────────────────────
        results: list[tuple[str, bool, float]] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            for plugin in plugins:
                ok, elapsed = self._deploy_plugin(plugin, tmp)
                results.append((plugin.name, ok, elapsed))

        # ── Hooks post_deploy globaux ─────────────────────────────
        console.print("\n[bold dim]Hooks post_deploy (global)[/bold dim]")
        self._hooks.run_hooks(self._cfg.hooks.post_deploy, "post_deploy global")

        # ── Rapport final ─────────────────────────────────────────
        self._print_report(results)
        return all(ok for _, ok, _ in results)

    def _deploy_plugin(self, plugin: "PluginEntry", tmp: Path) -> tuple[bool, float]:
        t0 = time.monotonic()
        console.print(f"\n[bold cyan]Plugin : {plugin.name}[/bold cyan]")

        source = (self._root / plugin.source).resolve()
        if not source.exists():
            console.print(f"  [red]✗[/red] Source introuvable : {source}")
            return False, time.monotonic() - t0

        # 1. Hooks pre_deploy du plugin
        if not self._hooks.run_hooks(plugin.hooks.pre_deploy, "pre_deploy"):
            console.print(f"  [red]✗[/red] Hook pre_deploy échoué — plugin skippé.")
            return False, time.monotonic() - t0

        # 2. Signature HMAC (optionnel)
        if plugin.sign:
            ok = self._sign_plugin(source)
            if not ok:
                return False, time.monotonic() - t0

        # 3. Archivage
        console.print(f"  [dim]▷[/dim] Archivage de {source.name}…")
        if not self._dry_run:
            archive = pack_plugin(source, tmp)
            size_kb = archive.stat().st_size // 1024
            console.print(f"  [dim]  {archive.name} ({size_kb} KB)[/dim]")
        else:
            console.print(f"  [dim]▷ (dry-run) archive {plugin.name}.tar.gz[/dim]")
            archive = tmp / f"{plugin.name}.tar.gz"

        # 4. Transfert SSH
        console.print(f"  [dim]▷[/dim] Transfert vers {self._target.host}…")
        ok = transfer_plugin(self._target, archive, plugin.name, self._dry_run)
        if not ok:
            return False, time.monotonic() - t0
        console.print(f"  [green]✓[/green] Transféré")

        # 5. Hot-reload via API XCore
        if plugin.reload and not self._no_reload:
            console.print(f"  [dim]▷[/dim] Hot-reload…")
            if not self._dry_run:
                ok = reload_plugin_remote(self._target, plugin.name)
            else:
                console.print(f"  [dim]▷ (dry-run) POST /plugins/{plugin.name}/reload[/dim]")
                ok = True
            if ok:
                console.print(f"  [green]✓[/green] Reloaded")
            else:
                console.print(f"  [yellow]⚠[/yellow] Reload échoué (plugin transféré mais non rechargé)")

        # 6. Hooks post_deploy du plugin
        self._hooks.run_hooks(plugin.hooks.post_deploy, "post_deploy")

        elapsed = time.monotonic() - t0
        console.print(f"  [green]✓[/green] [bold]{plugin.name}[/bold] déployé en {elapsed:.1f}s")
        return True, elapsed

    def _sign_plugin(self, source: Path) -> bool:
        console.print(f"  [dim]▷[/dim] Signature HMAC…")
        if self._dry_run:
            console.print(f"  [dim]▷ (dry-run) sign {source.name}[/dim]")
            return True
        try:
            from xcli._xcore import _require_xcore
            _require_xcore()
            from xcore.kernel.security.signature import sign_plugin
            from xcore.kernel.security.validation import ManifestValidator
            from xcore.configurations.loader import ConfigLoader

            cfg = ConfigLoader.load(None)
            secret = cfg.plugins.secret_key or b"change-me"
            manifest, _, _ = ManifestValidator().load_and_validate(source)
            sign_plugin(manifest, secret)
            console.print(f"  [green]✓[/green] Signé")
            return True
        except Exception as e:
            console.print(f"  [red]✗[/red] Signature échouée : {escape(str(e))}")
            return False

    def _print_report(self, results: list[tuple[str, bool, float]]) -> None:
        console.print()
        table = Table(title="Résultat du déploiement", show_lines=False)
        table.add_column("Plugin", style="cyan")
        table.add_column("Statut", justify="center")
        table.add_column("Durée", justify="right", style="dim")

        for name, ok, elapsed in results:
            status = "[green]✓ OK[/green]" if ok else "[red]✗ ERREUR[/red]"
            table.add_row(name, status, f"{elapsed:.1f}s")

        console.print(table)

        total = len(results)
        success = sum(1 for _, ok, _ in results if ok)
        if success == total:
            console.print(f"[green bold]✓ {success}/{total} plugins déployés avec succès.[/green bold]")
        else:
            console.print(f"[red bold]✗ {success}/{total} plugins réussis — {total - success} erreur(s).[/red bold]")
