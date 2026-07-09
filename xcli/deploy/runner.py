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
    from .config import (
        DeployConfig, ExtensionEntry, Hook, IntegrationConfig,
        PluginEntry, RepoSource, Target,
    )

console = Console()

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


# ── Git Clone ─────────────────────────────────────────────────────────────────


def clone_repo(repo: "RepoSource", dest: Path, ssh_key: str | None = None) -> Path:
    """
    Clone un repo Git dans dest/. Retourne le chemin du dossier cloné
    (ou du sous-dossier si repo.subdirectory est défini).
    """
    clone_dir = dest / "_repo_clone"
    clone_dir.mkdir(parents=True, exist_ok=True)

    url = repo.authenticated_url()

    cmd = [
        "git", "clone",
        "--depth", "1",
        "--branch", repo.ref,
        "--single-branch",
        url,
        str(clone_dir),
    ]

    env = None
    if repo.is_ssh and ssh_key:
        import os
        key_path = str(Path(ssh_key).expanduser())
        env = {
            **os.environ,
            "GIT_SSH_COMMAND": f"ssh -i {key_path} -o StrictHostKeyChecking=no",
        }

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        err = result.stderr.strip()
        raise RuntimeError(f"git clone échoué pour {repo.url}@{repo.ref} :\n{err}")

    if repo.subdirectory:
        target = clone_dir / repo.subdirectory
        if not target.exists():
            raise RuntimeError(
                f"Sous-dossier '{repo.subdirectory}' introuvable dans le repo cloné."
            )
        return target

    return clone_dir


# ── Packager ─────────────────────────────────────────────────────────────────


def pack_dir(source_path: Path, archive_name: str, dest: Path) -> Path:
    """Crée une archive tar.gz de source_path dans dest/. Retourne le chemin de l'archive."""
    archive_path = dest / f"{archive_name}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        for item in source_path.rglob("*"):
            if _should_exclude(item):
                continue
            arcname = item.relative_to(source_path.parent)
            tar.add(item, arcname=str(arcname))
    return archive_path


def pack_plugin(plugin_path: Path, dest: Path) -> Path:
    return pack_dir(plugin_path, plugin_path.name, dest)


# ── Remote API ────────────────────────────────────────────────────────────────


def reload_plugin_remote(target: "Target", plugin_name: str) -> bool:
    if not target.xcore_url:
        return True

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


def restart_extension_remote(target: "Target", extension_name: str) -> bool:
    """Appelle POST /services/{name}/restart sur l'instance XCore distante."""
    if not target.xcore_url:
        return True

    try:
        import httpx
    except ImportError:
        console.print("    [yellow]⚠ httpx non installé — restart API skippé[/yellow]")
        return True

    url = f"{target.xcore_url.rstrip('/')}/services/{extension_name}/restart"
    headers = {}
    if target.xcore_token:
        headers["Authorization"] = f"Bearer {target.xcore_token}"

    try:
        resp = httpx.post(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            return True
        console.print(f"    [red]✗[/red] API restart HTTP {resp.status_code}: {escape(resp.text[:200])}")
        return False
    except Exception as e:
        console.print(f"    [red]✗[/red] API restart erreur : {escape(str(e))}")
        return False


def reload_config_remote(target: "Target") -> bool:
    """Appelle POST /config/reload pour recharger integration.yaml sans redémarrage complet."""
    if not target.xcore_url:
        return True

    try:
        import httpx
    except ImportError:
        return True

    url = f"{target.xcore_url.rstrip('/')}/config/reload"
    headers = {}
    if target.xcore_token:
        headers["Authorization"] = f"Bearer {target.xcore_token}"

    try:
        resp = httpx.post(url, headers=headers, timeout=60)
        return resp.status_code == 200
    except Exception as e:
        console.print(f"    [red]✗[/red] config reload erreur : {escape(str(e))}")
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


def _ssh_exec(client, cmd: str) -> tuple[int, str]:
    stdin, stdout, stderr = client.exec_command(cmd)
    exit_code = stdout.channel.recv_exit_status()
    err = stderr.read().decode().strip()
    return exit_code, err


def transfer_archive(
    target: "Target",
    archive: Path,
    remote_dir: str,
    dry_run: bool,
) -> bool:
    """Transfère une archive tar.gz et l'extrait dans remote_dir."""
    remote_archive = f"/tmp/{archive.name}"

    if dry_run:
        console.print(f"    [dim]▷ (dry-run) sftp {archive.name} → {target.host}:{remote_dir}[/dim]")
        return True

    try:
        client = _ssh_client(target)
        sftp = client.open_sftp()

        exit_code, err = _ssh_exec(client, f"mkdir -p {remote_dir}")

        sftp.put(str(archive), remote_archive)
        sftp.close()

        cmd = f"tar -xzf {remote_archive} -C {remote_dir} --strip-components=1 && rm {remote_archive}"
        exit_code, err = _ssh_exec(client, cmd)
        client.close()

        if exit_code != 0:
            console.print(f"    [red]✗[/red] extraction échouée : {escape(err)}")
            return False
        return True

    except Exception as e:
        console.print(f"    [red]✗[/red] SSH erreur : {escape(str(e))}")
        return False


def transfer_plugin(target: "Target", archive: Path, plugin_name: str, dry_run: bool) -> bool:
    remote_dir = f"{target.plugins_root}/{plugin_name}"
    return transfer_archive(target, archive, remote_dir, dry_run)


def transfer_extension(target: "Target", archive: Path, ext_name: str, dry_run: bool) -> bool:
    remote_dir = f"{target.resolved_extensions_root()}/{ext_name}"
    return transfer_archive(target, archive, remote_dir, dry_run)


def transfer_integration_yaml(
    target: "Target",
    source: Path,
    remote_path: str,
    dry_run: bool,
) -> bool:
    """Transfère integration.yaml directement (pas d'archive)."""
    if dry_run:
        console.print(f"    [dim]▷ (dry-run) sftp {source.name} → {target.host}:{remote_path}[/dim]")
        return True

    try:
        client = _ssh_client(target)
        sftp = client.open_sftp()

        remote_dir = str(Path(remote_path).parent)
        _ssh_exec(client, f"mkdir -p {remote_dir}")

        sftp.put(str(source), remote_path)
        sftp.close()
        client.close()
        return True
    except Exception as e:
        console.print(f"    [red]✗[/red] SSH erreur : {escape(str(e))}")
        return False


def transfer_file(target: "Target", source: Path, remote_path: str, dry_run: bool) -> bool:
    """Transfère un fichier unique vers le serveur distant via SFTP."""
    if dry_run:
        console.print(f"    [dim]▷ (dry-run) sftp {source.name} → {target.host}:{remote_path}[/dim]")
        return True

    try:
        client = _ssh_client(target)
        sftp = client.open_sftp()

        remote_dir = str(Path(remote_path).parent)
        _ssh_exec(client, f"mkdir -p {remote_dir}")

        sftp.put(str(source), remote_path)
        sftp.close()
        client.close()
        return True
    except Exception as e:
        console.print(f"    [red]✗[/red] SSH erreur : {escape(str(e))}")
        return False


def restart_xcore_service(target: "Target", dry_run: bool) -> bool:
    """Redémarre le service xcore via systemctl (ou supervisorctl)."""
    if dry_run:
        console.print("    [dim]▷ (dry-run) systemctl restart xcore[/dim]")
        return True

    try:
        client = _ssh_client(target)
        # Essaie systemctl d'abord, puis supervisorctl
        exit_code, err = _ssh_exec(
            client,
            "systemctl restart xcore 2>/dev/null || supervisorctl restart xcore 2>/dev/null || true"
        )
        client.close()
        return True
    except Exception as e:
        console.print(f"    [red]✗[/red] SSH restart erreur : {escape(str(e))}")
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
        extensions = self._cfg.extensions_for_target(target.name)
        integration = self._cfg.integration_for_target(target.name)
        files = self._cfg.files_for_target(target.name)

        if self._plugin_filter:
            plugins = [p for p in plugins if p.name == self._plugin_filter]
            if not plugins:
                console.print(f"[red]Plugin '{self._plugin_filter}' introuvable dans la config.[/red]")
                return False
            extensions = []
            integration = None

        console.print(
            f"\n[bold]Déploiement → [cyan]{target.name}[/cyan] "
            f"([dim]{target.user}@{target.host}[/dim])[/bold]"
        )
        if self._dry_run:
            console.print("[yellow]  Mode dry-run — aucune action réelle[/yellow]")

        # ── Hooks pre_deploy globaux
        console.print("\n[bold dim]Hooks pre_deploy (global)[/bold dim]")
        if not self._hooks.run_hooks(self._cfg.hooks.pre_deploy, "pre_deploy global"):
            console.print("[red bold]✗ Hook pre_deploy global échoué — déploiement annulé.[/red bold]")
            return False

        results: list[tuple[str, str, bool, float]] = []  # (name, type, ok, elapsed)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            # ── integration.yaml en premier (avant les plugins/extensions)
            if integration:
                ok, elapsed = self._deploy_integration(integration, tmp)
                results.append(("integration.yaml", "config", ok, elapsed))

            # ── Fichiers (config, .env, etc.)
            for file_entry in files:
                ok, elapsed = self._deploy_file(file_entry)
                results.append((file_entry.source, "file", ok, elapsed))

            # ── Extensions (services)
            for ext in extensions:
                ok, elapsed = self._deploy_extension(ext, tmp)
                results.append((ext.name, "extension", ok, elapsed))

            # ── Plugins
            for plugin in plugins:
                ok, elapsed = self._deploy_plugin(plugin, tmp)
                results.append((plugin.name, "plugin", ok, elapsed))

        # ── Hooks post_deploy globaux
        console.print("\n[bold dim]Hooks post_deploy (global)[/bold dim]")
        self._hooks.run_hooks(self._cfg.hooks.post_deploy, "post_deploy global")

        self._print_report(results)
        return all(ok for _, _, ok, _ in results)

    def _resolve_source(
        self,
        entry_name: str,
        source: str | None,
        repo,  # RepoSource | None
        tmp: Path,
    ) -> Path | None:
        """
        Retourne le Path local vers le code source (clone si repo:, sinon chemin local).
        Retourne None en cas d'erreur.
        """
        if repo is not None:
            ssh_key = self._target.ssh_key if repo.is_ssh else None
            console.print(f"  [dim]▷[/dim] Clone {repo.url} @ {repo.ref}…")
            if self._dry_run:
                console.print(f"  [dim]▷ (dry-run) git clone {repo.url}[/dim]")
                return tmp / "_fake_source"
            try:
                return clone_repo(repo, tmp / entry_name, ssh_key=ssh_key)
            except RuntimeError as e:
                console.print(f"  [red]✗[/red] {escape(str(e))}")
                return None
        else:
            path = (self._root / source).resolve()
            if not path.exists():
                console.print(f"  [red]✗[/red] Source introuvable : {path}")
                return None
            return path

    def _deploy_plugin(self, plugin: "PluginEntry", tmp: Path) -> tuple[bool, float]:
        t0 = time.monotonic()
        console.print(f"\n[bold cyan]Plugin : {plugin.name}[/bold cyan]")

        source = self._resolve_source(plugin.name, plugin.source, plugin.repo, tmp)
        if source is None:
            return False, time.monotonic() - t0

        if not self._hooks.run_hooks(plugin.hooks.pre_deploy, "pre_deploy"):
            console.print(f"  [red]✗[/red] Hook pre_deploy échoué — plugin skippé.")
            return False, time.monotonic() - t0

        if plugin.sign:
            if not self._sign_plugin(source):
                return False, time.monotonic() - t0

        console.print(f"  [dim]▷[/dim] Archivage…")
        if not self._dry_run:
            archive = pack_dir(source, plugin.name, tmp)
            size_kb = archive.stat().st_size // 1024
            console.print(f"  [dim]  {archive.name} ({size_kb} KB)[/dim]")
        else:
            console.print(f"  [dim]▷ (dry-run) archive {plugin.name}.tar.gz[/dim]")
            archive = tmp / f"{plugin.name}.tar.gz"

        console.print(f"  [dim]▷[/dim] Transfert vers {self._target.host}…")
        ok = transfer_plugin(self._target, archive, plugin.name, self._dry_run)
        if not ok:
            return False, time.monotonic() - t0
        console.print(f"  [green]✓[/green] Transféré")

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

        self._hooks.run_hooks(plugin.hooks.post_deploy, "post_deploy")

        elapsed = time.monotonic() - t0
        console.print(f"  [green]✓[/green] [bold]{plugin.name}[/bold] déployé en {elapsed:.1f}s")
        return True, elapsed

    def _deploy_extension(self, ext: "ExtensionEntry", tmp: Path) -> tuple[bool, float]:
        t0 = time.monotonic()
        console.print(f"\n[bold magenta]Extension : {ext.name}[/bold magenta]")

        source = self._resolve_source(ext.name, ext.source, ext.repo, tmp)
        if source is None:
            return False, time.monotonic() - t0

        if not self._hooks.run_hooks(ext.hooks.pre_deploy, "pre_deploy"):
            console.print(f"  [red]✗[/red] Hook pre_deploy échoué — extension skippée.")
            return False, time.monotonic() - t0

        console.print(f"  [dim]▷[/dim] Archivage…")
        if not self._dry_run:
            archive = pack_dir(source, ext.name, tmp)
            size_kb = archive.stat().st_size // 1024
            console.print(f"  [dim]  {archive.name} ({size_kb} KB)[/dim]")
        else:
            console.print(f"  [dim]▷ (dry-run) archive {ext.name}.tar.gz[/dim]")
            archive = tmp / f"{ext.name}.tar.gz"

        console.print(f"  [dim]▷[/dim] Transfert vers {self._target.host}…")
        ok = transfer_extension(self._target, archive, ext.name, self._dry_run)
        if not ok:
            return False, time.monotonic() - t0
        console.print(f"  [green]✓[/green] Transféré")

        if ext.restart and not self._no_reload:
            console.print(f"  [dim]▷[/dim] Restart service…")
            if not self._dry_run:
                ok = restart_extension_remote(self._target, ext.name)
            else:
                console.print(f"  [dim]▷ (dry-run) POST /services/{ext.name}/restart[/dim]")
                ok = True
            status = "[green]✓[/green] Restarted" if ok else "[yellow]⚠[/yellow] Restart échoué"
            console.print(f"  {status}")

        self._hooks.run_hooks(ext.hooks.post_deploy, "post_deploy")

        elapsed = time.monotonic() - t0
        console.print(f"  [green]✓[/green] [bold]{ext.name}[/bold] déployée en {elapsed:.1f}s")
        return True, elapsed

    def _deploy_integration(self, cfg: "IntegrationConfig", tmp: Path) -> tuple[bool, float]:
        t0 = time.monotonic()
        console.print(f"\n[bold yellow]Config : integration.yaml[/bold yellow]")

        source = (self._root / cfg.source).resolve()
        if not source.exists():
            console.print(f"  [red]✗[/red] Fichier introuvable : {source}")
            return False, time.monotonic() - t0

        console.print(f"  [dim]▷[/dim] Transfert de integration.yaml…")
        ok = transfer_integration_yaml(self._target, source, cfg.remote_path, self._dry_run)
        if not ok:
            return False, time.monotonic() - t0
        console.print(f"  [green]✓[/green] Transféré → {cfg.remote_path}")

        if cfg.restart_xcore and not self._no_reload:
            console.print(f"  [dim]▷[/dim] Rechargement de la config XCore…")
            # Essaie d'abord un reload à chaud via API, sinon redémarre le service
            reloaded = False
            if not self._dry_run:
                reloaded = reload_config_remote(self._target)

            if reloaded:
                console.print(f"  [green]✓[/green] Config rechargée (API /config/reload)")
            else:
                # Fallback : restart du service système
                console.print(f"  [dim]▷[/dim] Fallback : restart service xcore…")
                restart_xcore_service(self._target, self._dry_run)
                console.print(f"  [green]✓[/green] Service redémarré")

        elapsed = time.monotonic() - t0
        console.print(f"  [green]✓[/green] [bold]integration.yaml[/bold] synchronisé en {elapsed:.1f}s")
        return True, elapsed

    def _deploy_file(self, file_entry) -> tuple[bool, float]:
        t0 = time.monotonic()
        console.print(f"\n[bold blue]Fichier : {file_entry.source}[/bold blue]")

        source = (self._root / file_entry.source).resolve()
        if not source.exists():
            console.print(f"  [red]✗[/red] Fichier introuvable : {source}")
            return False, time.monotonic() - t0

        console.print(f"  [dim]▷[/dim] Transfert…")
        ok = transfer_file(self._target, source, file_entry.dest, self._dry_run)
        if not ok:
            return False, time.monotonic() - t0

        elapsed = time.monotonic() - t0
        console.print(f"  [green]✓[/green] [bold]{file_entry.source}[/bold] → {file_entry.dest} ({elapsed:.1f}s)")
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

    def _print_report(self, results: list[tuple[str, str, bool, float]]) -> None:
        console.print()
        table = Table(title="Résultat du déploiement", show_lines=False)
        table.add_column("Nom", style="cyan")
        table.add_column("Type", style="dim")
        table.add_column("Statut", justify="center")
        table.add_column("Durée", justify="right", style="dim")

        for name, kind, ok, elapsed in results:
            status = "[green]✓ OK[/green]" if ok else "[red]✗ ERREUR[/red]"
            table.add_row(name, kind, status, f"{elapsed:.1f}s")

        console.print(table)

        total = len(results)
        success = sum(1 for _, _, ok, _ in results if ok)
        if success == total:
            console.print(f"[green bold]✓ {success}/{total} éléments déployés avec succès.[/green bold]")
        else:
            console.print(f"[red bold]✗ {success}/{total} réussis — {total - success} erreur(s).[/red bold]")
