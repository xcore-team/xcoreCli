"""
cli.py — Commandes Typer pour xcli deploy.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape
from typer import Typer

console = Console()

_CTX = {"help_option_names": ["-h", "--help"]}
app = Typer(help="Deploy XCore plugins to remote servers.", context_settings=_CTX)

_DEPLOY_FILE_DEFAULT = "xcore-deploy.yaml"


def _find_deploy_file(path: str | None) -> Path:
    if path:
        p = Path(path).resolve()
        if not p.exists():
            console.print(f"[red]Fichier introuvable :[/red] {path}")
            raise typer.Exit(1) from None
        return p

    # Recherche automatique depuis le répertoire courant
    for candidate in [
        Path.cwd() / _DEPLOY_FILE_DEFAULT,
        Path.cwd() / "deploy" / _DEPLOY_FILE_DEFAULT,
    ]:
        if candidate.exists():
            return candidate

    console.print(
        f"[red]Fichier de déploiement introuvable.[/red]\n"
        f"  Crée-le avec : [cyan]xcli deploy init[/cyan]\n"
        f"  Ou spécifie-le : [cyan]xcli deploy run <target> --file chemin/xcore-deploy.yaml[/cyan]"
    )
    raise typer.Exit(1)


# ── xcli deploy init ──────────────────────────────────────────────────────────


@app.command("init")
def init(
    output: str = typer.Option(
        _DEPLOY_FILE_DEFAULT, "--output", "-o", help="Chemin du fichier à créer"
    ),
) -> None:
    """Génère un fichier xcore-deploy.yaml d'exemple dans le répertoire courant."""
    out = Path(output)
    if out.exists():
        overwrite = typer.confirm(f"{out} existe déjà. Écraser ?", default=False)
        if not overwrite:
            raise typer.Exit(0)

    template = """\
version: "1"

# ── Serveurs de déploiement ─────────────────────────────────────────────────
targets:
  production:
    host: prod.monapp.com
    port: 22
    user: deploy
    ssh_key: ~/.ssh/id_ed25519              # ou password: "${DEPLOY_SSH_PASS}"
    xcore_url: https://api.monapp.com       # URL de l'API XCore distante
    xcore_token: "${XCORE_ADMIN_TOKEN}"     # Bearer token admin — depuis l'env
    plugins_root: /opt/xcore/app/plugins
    extensions_root: /opt/xcore/app/extensions  # défaut: ../extensions si omis

  staging:
    host: staging.monapp.com
    port: 22
    user: deploy
    ssh_key: ~/.ssh/id_ed25519
    xcore_url: https://staging.monapp.com
    xcore_token: "${XCORE_STAGING_TOKEN}"
    plugins_root: /opt/xcore/app/plugins

# ── Hooks globaux ────────────────────────────────────────────────────────────
hooks:
  pre_deploy:
    - cmd: "uv run xcli plugin security validate --save"
    # - cmd: "uv run pytest tests/ -x -q"
    #   ignore_errors: false

  post_deploy:
    - cmd: "uv run xcli deploy status production"
      ignore_errors: true
    # - cmd: "curl -s -X POST https://hooks.slack.com/... -d '{\"text\":\"Deployed!\"}'"
    #   ignore_errors: true

# ── Config XCore (integration.yaml) ──────────────────────────────────────────
# Synchronise integration.yaml avant les extensions et plugins.
# restart_xcore: true → tente POST /config/reload, sinon restart service.
# integration:
#   source: ./integration.yaml
#   remote_path: /opt/xcore/integration.yaml
#   restart_xcore: true
#   # only: [production]

# ── Fichiers (config, .env, etc.) ──────────────────────────────────────────────
# Copiés vers le serveur avant les extensions et plugins.
# files:
#   - source: ./.env
#     dest: /opt/xcore/.env
#     # only: [production]
#
#   - source: ./config/prod.yaml
#     dest: /opt/xcore/config/prod.yaml

# ── Extensions (services XCore) ───────────────────────────────────────────────
# Déployées avant les plugins. Acceptent source: local ou repo: GitHub.
# extensions:
#   - name: mail
#     source: ./extensions/mail          # source locale
#     restart: true
#
#   - name: pubsub
#     repo: https://github.com/org/xcore-pubsub  # GitHub public
#     ref: v1.0.0
#     restart: true
#
#   - name: private-ext
#     repo: https://github.com/org/private-ext   # GitHub privé via token
#     ref: main
#     token: "${GITHUB_TOKEN}"
#     restart: true

# ── Plugins ───────────────────────────────────────────────────────────────────
# Acceptent source: (local) ou repo: (GitHub public/privé/SSH).
plugins:
  - name: billing-plugin
    source: ./app/plugins/billing         # source locale
    sign: true                            # signer avant transfert (HMAC)
    reload: true                          # hot-reload via API XCore après transfert
    # only: [production]                  # targets autorisés (vide = tous)
    hooks:
      pre_deploy:
        - cmd: "uv run xcli plugin security validate ./app/plugins/billing"
      post_deploy:
        - cmd: "echo 'billing-plugin déployé'"
          ignore_errors: true

  - name: auth-plugin
    source: ./app/plugins/auth
    sign: true
    reload: true

  # ── Exemple : plugin depuis GitHub public ────────────────────────────────
  # - name: my-oss-plugin
  #   repo: https://github.com/org/xcore-my-plugin
  #   ref: v2.1.0
  #   sign: false
  #   reload: true

  # ── Exemple : plugin GitHub privé via token ──────────────────────────────
  # - name: my-private-plugin
  #   repo: https://github.com/org/private-plugin
  #   ref: main
  #   token: "${GITHUB_TOKEN}"
  #   sign: true
  #   reload: true

  # ── Exemple : plugin GitHub privé via SSH ────────────────────────────────
  # - name: my-ssh-plugin
  #   repo: git@github.com:org/private-plugin.git
  #   ref: main                              # utilise ssh_key du target
  #   sign: true
  #   reload: true

  # ── Exemple : plugin dans un sous-dossier du repo ────────────────────────
  # - name: my-sub-plugin
  #   repo: https://github.com/org/monorepo
  #   ref: main
  #   subdirectory: packages/my-plugin
  #   reload: true

  - name: pdf-generator
    source: ./app/plugins/pdf-generator
    sign: false
    reload: true
    only: [production]
"""
    out.write_text(template, encoding="utf-8")
    console.print(f"[green]✓[/green] Fichier créé : [dim]{out}[/dim]")
    console.print(
        "\n[dim]Étapes suivantes :[/dim]\n"
        "  1. Édite [cyan]xcore-deploy.yaml[/cyan] avec tes targets et plugins\n"
        "  2. [cyan]xcli deploy run staging[/cyan]        → déploie sur staging\n"
        "  3. [cyan]xcli deploy run production[/cyan]     → déploie en production\n"
        "  4. [cyan]xcli deploy run production --dry-run[/cyan]  → simule sans rien envoyer"
    )


# ── xcli deploy list ──────────────────────────────────────────────────────────


@app.command("list")
def list_targets(
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Chemin vers xcore-deploy.yaml"),
) -> None:
    """Liste les targets et plugins déclarés dans xcore-deploy.yaml."""
    from rich.table import Table
    from .config import DeployConfig

    deploy_file = _find_deploy_file(file)
    try:
        cfg = DeployConfig.load(deploy_file)
    except Exception as e:
        console.print(f"[red]Erreur de config :[/red] {escape(str(e))}")
        raise typer.Exit(1) from None

    # Targets
    t = Table(title="Targets", show_lines=False)
    t.add_column("Nom", style="cyan")
    t.add_column("Host")
    t.add_column("User", style="dim")
    t.add_column("Plugins root", style="dim")
    t.add_column("XCore URL", style="dim")

    for name, target in cfg.targets.items():
        t.add_row(
            name,
            f"{target.host}:{target.port}",
            target.user,
            target.plugins_root,
            target.xcore_url or "—",
        )
    console.print(t)

    # integration.yaml
    if cfg.integration:
        ig = cfg.integration
        console.print(
            f"\n[bold dim]integration.yaml[/bold dim]  "
            f"[dim]{ig.source} → {ig.remote_path}[/dim]  "
            f"restart_xcore=[cyan]{'true' if ig.restart_xcore else 'false'}[/cyan]"
            + (f"  only=[dim]{', '.join(ig.only)}[/dim]" if ig.only else "")
        )

    # Extensions
    if cfg.extensions:
        e = Table(title="Extensions (services)", show_lines=False)
        e.add_column("Nom", style="magenta")
        e.add_column("Source / Repo", style="dim")
        e.add_column("Ref", style="dim")
        e.add_column("Restart", justify="center")
        e.add_column("Only")
        e.add_column("Hooks", justify="right", style="dim")

        for ext in cfg.extensions:
            if ext.repo:
                src = ext.repo.url
                ref = ext.repo.ref
            else:
                src = ext.source or "?"
                ref = "—"
            e.add_row(
                ext.name,
                src,
                ref,
                "[green]✓[/green]" if ext.restart else "—",
                ", ".join(ext.only) if ext.only else "tous",
                f"{len(ext.hooks.pre_deploy)}+{len(ext.hooks.post_deploy)}",
            )
        console.print(e)

    # Plugins
    p = Table(title="Plugins", show_lines=False)
    p.add_column("Nom", style="cyan")
    p.add_column("Source / Repo", style="dim")
    p.add_column("Ref", style="dim")
    p.add_column("Sign", justify="center")
    p.add_column("Reload", justify="center")
    p.add_column("Only")
    p.add_column("Hooks", justify="right", style="dim")

    for plugin in cfg.plugins:
        if plugin.repo:
            src = plugin.repo.url
            ref = plugin.repo.ref
        else:
            src = plugin.source or "?"
            ref = "—"
        p.add_row(
            plugin.name,
            src,
            ref,
            "[green]✓[/green]" if plugin.sign else "—",
            "[green]✓[/green]" if plugin.reload else "—",
            ", ".join(plugin.only) if plugin.only else "tous",
            f"{len(plugin.hooks.pre_deploy)}+{len(plugin.hooks.post_deploy)}",
        )
    console.print(p)

    # Fichiers
    if cfg.files:
        f = Table(title="Fichiers (copiés avant extensions/plugins)", show_lines=False)
        f.add_column("Source", style="blue")
        f.add_column("Dest", style="dim")
        f.add_column("Only")
        for file_entry in cfg.files:
            f.add_row(file_entry.source, file_entry.dest, ", ".join(file_entry.only) if file_entry.only else "tous")
        console.print(f)

    # Hooks globaux
    if cfg.hooks.pre_deploy or cfg.hooks.post_deploy:
        console.print("\n[bold dim]Hooks globaux[/bold dim]")
        for h in cfg.hooks.pre_deploy:
            console.print(f"  pre_deploy  → {escape(h.cmd)}")
        for h in cfg.hooks.post_deploy:
            console.print(f"  post_deploy → {escape(h.cmd)}")


# ── xcli deploy status ────────────────────────────────────────────────────────


@app.command("status")
def status(
    target_name: str = typer.Argument(..., help="Nom du target (ex: production)"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Chemin vers xcore-deploy.yaml"),
) -> None:
    """Affiche l'état des plugins sur un serveur distant via l'API XCore."""
    from .config import DeployConfig

    deploy_file = _find_deploy_file(file)
    try:
        cfg = DeployConfig.load(deploy_file)
        target = cfg.get_target(target_name)
    except Exception as e:
        console.print(f"[red]Erreur :[/red] {escape(str(e))}")
        raise typer.Exit(1) from None

    if not target.xcore_url:
        console.print(f"[yellow]⚠ xcore_url non configuré pour le target '{target_name}'.[/yellow]")
        raise typer.Exit(1) from None

    try:
        import httpx
    except ImportError:
        console.print("[red]httpx requis : pip install httpx[/red]")
        raise typer.Exit(1) from None

    url = f"{target.xcore_url.rstrip('/')}/plugins/ipc/status"
    headers = {}
    if target.xcore_token:
        headers["Authorization"] = f"Bearer {target.xcore_token}"

    try:
        resp = httpx.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        console.print(f"[red]✗[/red] Connexion échouée : {escape(str(e))}")
        raise typer.Exit(1) from None

    from rich.table import Table

    plugins = data.get("plugins", [])
    table = Table(title=f"Plugins sur {target_name} ({data.get('count', 0)})")
    table.add_column("Nom", style="cyan")
    table.add_column("State", justify="center")
    table.add_column("Mode", style="dim")

    for p in plugins:
        state = p.get("state", "?")
        color = "green" if state in ("ready", "running") else "yellow"
        table.add_row(p.get("name", "?"), f"[{color}]{state}[/{color}]", p.get("mode", "?"))

    console.print(table)


# ── xcli deploy run <target> ──────────────────────────────────────────────────


@app.callback(invoke_without_command=True)
def callback(ctx: typer.Context) -> None:
    """Deploy XCore plugins to remote servers."""
    if ctx.invoked_subcommand is not None:
        return
    console.print(ctx.get_help())
    raise typer.Exit(0)


@app.command("run")
def deploy(
    target_name: str = typer.Argument(..., help="Nom du target (ex: production, staging)"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Chemin vers xcore-deploy.yaml"),
    plugin: Optional[str] = typer.Option(None, "--plugin", "-p", help="Déploie uniquement ce plugin"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simule sans rien envoyer"),
    no_reload: bool = typer.Option(False, "--no-reload", help="Transfère sans déclencher le hot-reload"),
) -> None:
    """
    Déploie les plugins XCore vers un serveur distant.

    Exemples :
      xcli deploy run production
      xcli deploy run staging --plugin billing-plugin
      xcli deploy run production --dry-run
      xcli deploy run production --no-reload
    """
    from .config import DeployConfig
    from .runner import DeployRunner

    deploy_file = _find_deploy_file(file)
    try:
        cfg = DeployConfig.load(deploy_file)
    except Exception as e:
        console.print(f"[red]Erreur de config :[/red] {escape(str(e))}")
        raise typer.Exit(1) from None

    project_root = deploy_file.parent

    runner = DeployRunner(
        config=cfg,
        target_name=target_name,
        project_root=project_root,
        dry_run=dry_run,
        no_reload=no_reload,
        plugin_filter=plugin,
    )

    try:
        success = runner.run()
    except KeyError as e:
        console.print(f"[red]Erreur :[/red] {escape(str(e))}")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]Erreur inattendue :[/red] {escape(str(e))}")
        raise typer.Exit(1) from None

    if not success:
        raise typer.Exit(1) from None


# ── xcli deploy copy <target> <source> <dest> ──────────────────────────────────


@app.command("copy")
def copy(
    target_name: str = typer.Argument(..., help="Nom du target (ex: production)"),
    source: str = typer.Argument(..., help="Chemin local du fichier à copier"),
    dest: str = typer.Argument(..., help="Chemin distant de destination"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Chemin vers xcore-deploy.yaml"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simule sans rien envoyer"),
) -> None:
    """
    Copie un fichier vers un serveur distant via SFTP.

    Exemples :
      xcli deploy copy production .env /opt/xcore/.env
      xcli deploy copy staging config.yaml /opt/xcore/config.yaml --dry-run
    """
    from .config import DeployConfig
    from .runner import transfer_file

    deploy_file = _find_deploy_file(file)
    try:
        cfg = DeployConfig.load(deploy_file)
        target = cfg.get_target(target_name)
    except Exception as e:
        console.print(f"[red]Erreur :[/red] {escape(str(e))}")
        raise typer.Exit(1) from None

    source_path = Path(source).resolve()
    if not source_path.exists():
        console.print(f"[red]Fichier source introuvable :[/red] {source}")
        raise typer.Exit(1)

    console.print(f"\n[bold]Copie → [cyan]{target_name}[/cyan] ([dim]{target.user}@{target.host}[/dim])[/bold]")
    if dry_run:
        console.print("[yellow]  Mode dry-run — aucune action réelle[/yellow]")

    ok = transfer_file(target, source_path, dest, dry_run)
    if ok:
        console.print(f"\n[green]✓[/green] [bold]{source}[/bold] → [dim]{target.host}:{dest}[/dim]")
    else:
        raise typer.Exit(1)
