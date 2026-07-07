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
            raise typer.Exit(1)
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
        f"  Ou spécifie-le : [cyan]xcli deploy <target> --file chemin/xcore-deploy.yaml[/cyan]"
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
    ssh_key: ~/.ssh/id_ed25519          # ou password: "${DEPLOY_SSH_PASS}"
    xcore_url: https://api.monapp.com   # URL de l'API XCore distante (pour le reload)
    xcore_token: "${XCORE_ADMIN_TOKEN}" # Bearer token admin
    plugins_root: /opt/xcore/app/plugins

  staging:
    host: staging.monapp.com
    port: 22
    user: deploy
    ssh_key: ~/.ssh/id_ed25519
    xcore_url: https://staging.monapp.com
    xcore_token: "${XCORE_STAGING_TOKEN}"
    plugins_root: /opt/xcore/app/plugins

# ── Hooks globaux (exécutés pour chaque déploiement) ────────────────────────
# Les commandes sont exécutées dans le répertoire du projet.
# ignore_errors: true → continue même si la commande échoue.
hooks:
  pre_deploy:
    - cmd: "uv run xcli plugin security validate --save"
    - cmd: "uv run xcli plugin security sign ./app/plugins/billing"
      ignore_errors: false
    # - cmd: "python scripts/run_tests.py"
    #   cwd: "./tests"

  post_deploy:
    - cmd: "uv run xcli plugin runtime status"
    # - cmd: "curl -s -X POST https://hooks.slack.com/... -d '{\"text\":\"Deployed!\"}'"
    #   ignore_errors: true

# ── Plugins à déployer ───────────────────────────────────────────────────────
plugins:
  - name: billing-plugin
    source: ./app/plugins/billing       # chemin local vers le dossier du plugin
    sign: true                          # signer avant transfert (HMAC)
    reload: true                        # hot-reload via API XCore après transfert
    # only: [production]                # déployer sur ces targets uniquement (vide = tous)
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
        "  2. [cyan]xcli deploy staging[/cyan]        → déploie sur staging\n"
        "  3. [cyan]xcli deploy production[/cyan]     → déploie en production\n"
        "  4. [cyan]xcli deploy production --dry-run[/cyan]  → simule sans rien envoyer"
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
        raise typer.Exit(1)

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

    # Plugins
    p = Table(title="Plugins", show_lines=False)
    p.add_column("Nom", style="cyan")
    p.add_column("Source", style="dim")
    p.add_column("Sign", justify="center")
    p.add_column("Reload", justify="center")
    p.add_column("Only")
    p.add_column("Hooks pre", justify="right", style="dim")
    p.add_column("Hooks post", justify="right", style="dim")

    for plugin in cfg.plugins:
        p.add_row(
            plugin.name,
            plugin.source,
            "[green]✓[/green]" if plugin.sign else "—",
            "[green]✓[/green]" if plugin.reload else "—",
            ", ".join(plugin.only) if plugin.only else "tous",
            str(len(plugin.hooks.pre_deploy)),
            str(len(plugin.hooks.post_deploy)),
        )
    console.print(p)

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
        raise typer.Exit(1)

    if not target.xcore_url:
        console.print(f"[yellow]⚠ xcore_url non configuré pour le target '{target_name}'.[/yellow]")
        raise typer.Exit(1)

    try:
        import httpx
    except ImportError:
        console.print("[red]httpx requis : pip install httpx[/red]")
        raise typer.Exit(1)

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
        raise typer.Exit(1)

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


# ── xcli deploy <target> ──────────────────────────────────────────────────────


@app.command("run", help="Déploie les plugins vers un target. Alias : xcli deploy <target>")
@app.callback(invoke_without_command=True)
def deploy(
    ctx: typer.Context,
    target_name: Optional[str] = typer.Argument(None, help="Nom du target (ex: production, staging)"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Chemin vers xcore-deploy.yaml"),
    plugin: Optional[str] = typer.Option(None, "--plugin", "-p", help="Déploie uniquement ce plugin"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simule sans rien envoyer"),
    no_reload: bool = typer.Option(False, "--no-reload", help="Transfère sans déclencher le hot-reload"),
) -> None:
    """
    Déploie les plugins XCore vers un serveur distant.

    Exemples :
      xcli deploy production
      xcli deploy staging --plugin billing-plugin
      xcli deploy production --dry-run
      xcli deploy production --no-reload
    """
    if ctx.invoked_subcommand is not None:
        return  # une sous-commande a été invoquée (init, list, status)

    if not target_name:
        console.print(ctx.get_help())
        raise typer.Exit(0)

    from .config import DeployConfig
    from .runner import DeployRunner

    deploy_file = _find_deploy_file(file)
    try:
        cfg = DeployConfig.load(deploy_file)
    except Exception as e:
        console.print(f"[red]Erreur de config :[/red] {escape(str(e))}")
        raise typer.Exit(1)

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
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Erreur inattendue :[/red] {escape(str(e))}")
        raise typer.Exit(1)

    if not success:
        raise typer.Exit(1)
