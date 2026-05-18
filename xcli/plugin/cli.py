import re
import sys
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.tree import Tree
from typer import Typer

from xcli._run import ns, run
from .scaffold import scaffold

_CTX = {"help_option_names": ["-h", "--help"]}
app = Typer(help="Plugin management.", context_settings=_CTX)
console = Console()

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_CONFIG_CANDIDATES = [
    "integration.yaml", "integration.json",
    "config/integration.yaml", "config/integration.json",
]


def _plugins_dir() -> Path:
    for candidate in _CONFIG_CANDIDATES:
        path = Path(candidate)
        if not path.exists():
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            d = raw.get("plugins", {}).get("directory")
            if d:
                return Path(d)
        except Exception:
            pass
    console.print("[yellow]⚠[/yellow] No integration.yaml — run [cyan]xcli init[/cyan] first.")
    sys.exit(1)


def _print_tree(root: Path, created: list[Path]) -> None:
    tree = Tree(f"[bold green]{root.name}/[/bold green]")
    dirs: dict = {}
    for path in sorted(created):
        rel = path.relative_to(root)
        parts = rel.parts
        current = tree
        for i, part in enumerate(parts[:-1]):
            key = "/".join(parts[: i + 1])
            if key not in dirs:
                dirs[key] = current.add(f"[cyan]{part}/[/cyan]")
            current = dirs[key]
        current.add(f"[white]{parts[-1]}[/white]")
    console.print(tree)


# ── new ───────────────────────────────────────────────────────

@app.command("new")
def new() -> None:
    """Scaffold a new plugin in the directory from integration.yaml."""
    console.print("\n[bold]xcli plugin new[/bold]\n")
    plugins_root = _plugins_dir()

    while True:
        name = Prompt.ask("Plugin name  [dim](lowercase, underscores)[/dim]")
        if _NAME_RE.match(name):
            break
        console.print("[red]Lowercase letters, digits and underscores only.[/red]")

    mode = Prompt.ask(
        "Execution mode", choices=["trusted", "sandboxed", "legacy"], default="trusted"
    )
    target = plugins_root / name

    if target.exists() and not Confirm.ask(f"[yellow]{target}[/yellow] exists. Continue?", default=False):
        sys.exit(0)

    created = scaffold({"name": name, "execution_mode": mode}, target)
    console.print()
    _print_tree(target, created)
    console.print(f"\n[green]✓[/green] [cyan]{target}[/cyan] ready.")


# ── list ──────────────────────────────────────────────────────

@app.command("list")
def list_plugins() -> None:
    """List installed plugins."""
    from xcore.cli.plugin_cmd import handle_plugin
    run(handle_plugin(ns(subcommand="list")))


# ── health ────────────────────────────────────────────────────

@app.command("health")
def health() -> None:
    """Health-check all installed plugins."""
    from xcore.cli.plugin_cmd import handle_plugin
    run(handle_plugin(ns(subcommand="health")))


# ── install ───────────────────────────────────────────────────

def _resolve_marketplace_version(name: str, version: str) -> tuple[str, str]:
    """
    Returns (download_url, source_type) for the requested version.
    Talks to the marketplace configured in integration.yaml.
    """
    import asyncio
    from xcore.configurations.loader import ConfigLoader
    from xcore.marketplace import MarketplaceClient

    cfg = ConfigLoader.load(None)
    client = MarketplaceClient(cfg)

    async def _fetch():
        if version == "latest":
            data = await client.get_plugin(name)
            if not data:
                console.print(f"[red]Plugin '[cyan]{name}[/cyan]' not found on marketplace.[/red]")
                raise typer.Exit(1)
            return data.get("download_url"), data.get("source_type", "zip")

        versions = await client.get_versions(name)
        match = next((v for v in versions if v.get("version") == version), None)
        if not match:
            available = ", ".join(v.get("version", "?") for v in versions) or "none"
            console.print(f"[red]Version [cyan]{version}[/cyan] not found for [cyan]{name}[/cyan].[/red]")
            console.print(f"Available: {available}")
            console.print(f"Tip: [dim]xcli plugin versions {name}[/dim]")
            raise typer.Exit(1)
        return match.get("download_url"), match.get("source_type", "zip")

    return asyncio.run(_fetch())


@app.command("install")
def install(
    plugin_spec: str = typer.Argument(..., help="Plugin to install: name, name@latest, or name@1.2.3"),
    source: str = typer.Option("marketplace", "--source", "-s", help="marketplace | git | zip"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="URL for git/zip source"),
) -> None:
    """Install a plugin — supports name@version syntax for marketplace."""
    from xcore.cli.plugin_cmd import handle_plugin

    # Parse name@version
    if "@" in plugin_spec:
        name, version = plugin_spec.split("@", 1)
    else:
        name, version = plugin_spec, None

    if version and source == "marketplace":
        console.print(f"Resolving [cyan]{name}@{version}[/cyan] on marketplace...")
        resolved_url, resolved_source = _resolve_marketplace_version(name, version)
        if not resolved_url:
            console.print(f"[red]No download URL found for {name}@{version}.[/red]")
            raise typer.Exit(1)
        console.print(f"  → [dim]{resolved_url}[/dim]")
        run(handle_plugin(ns(subcommand="install", name=name, source=resolved_source, url=resolved_url)))
    else:
        run(handle_plugin(ns(subcommand="install", name=name, source=source, url=url)))


# ── versions ──────────────────────────────────────────────────

@app.command("versions")
def versions(name: str) -> None:
    """List available versions of a marketplace plugin."""
    async def _run():
        from rich.table import Table
        from xcore.configurations.loader import ConfigLoader
        from xcore.marketplace import MarketplaceClient

        cfg = ConfigLoader.load(None)
        client = MarketplaceClient(cfg)

        with console.status(f"Fetching versions for [cyan]{name}[/cyan]..."):
            data = await client.get_versions(name)

        if not data:
            console.print(f"[yellow]No versions found for '[cyan]{name}[/cyan]'.[/yellow]")
            return

        table = Table(title=f"Versions — {name}")
        table.add_column("Version", style="cyan")
        table.add_column("Released", style="dim")
        table.add_column("Source", style="green")
        table.add_column("Download URL", style="dim", no_wrap=False)
        for v in data:
            table.add_row(
                v.get("version", "?"),
                v.get("released_at", "—"),
                v.get("source_type", "zip"),
                v.get("download_url", "—"),
            )
        console.print(table)
        console.print(f"\n[dim]Install: xcli plugin install {name}@<version>[/dim]")

    run(_run())


# ── update / update-all ───────────────────────────────────────

def _installed_version(name: str) -> str | None:
    """Return the version string from the installed plugin.yaml, or None."""
    plugin_dir = _plugins_dir() / name
    manifest_path = plugin_dir / "plugin.yaml"
    if not manifest_path.exists():
        return None
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        return str(raw.get("version", "?"))
    except Exception:
        return None


def _do_update(name: str, target_version: str | None) -> None:
    """Core update logic: resolve version, remove, reinstall."""
    import asyncio
    import shutil
    from xcore.cli.plugin_cmd import handle_plugin
    from xcore.configurations.loader import ConfigLoader
    from xcore.marketplace import MarketplaceClient

    current = _installed_version(name)
    cfg = ConfigLoader.load(None)
    client = MarketplaceClient(cfg)

    async def _resolve():
        if target_version and target_version != "latest":
            versions = await client.get_versions(name)
            match = next((v for v in versions if v.get("version") == target_version), None)
            if not match:
                available = ", ".join(v.get("version", "?") for v in versions)
                console.print(f"[red]Version [cyan]{target_version}[/cyan] not found.[/red]")
                console.print(f"Available: {available}")
                raise typer.Exit(1)
            return match.get("download_url"), match.get("source_type", "zip"), target_version
        else:
            data = await client.get_plugin(name)
            if not data:
                console.print(f"[red]Plugin '[cyan]{name}[/cyan]' not found on marketplace.[/red]")
                raise typer.Exit(1)
            return data.get("download_url"), data.get("source_type", "zip"), data.get("version", "latest")

    url, source_type, new_version = asyncio.run(_resolve())

    if current and current == new_version:
        console.print(f"[green]✓[/green] [cyan]{name}[/cyan] is already at version [magenta]{current}[/magenta].")
        return

    console.print(f"Updating [cyan]{name}[/cyan]: [dim]{current or '?'}[/dim] → [magenta]{new_version}[/magenta]")
    if not url:
        console.print(f"[red]No download URL for {name}@{new_version}.[/red]")
        raise typer.Exit(1)

    plugin_path = _plugins_dir() / name
    if plugin_path.exists():
        shutil.rmtree(plugin_path)

    run(handle_plugin(ns(subcommand="install", name=name, source=source_type, url=url)))
    console.print(f"[green]✓[/green] [cyan]{name}[/cyan] updated to [magenta]{new_version}[/magenta].")


@app.command("update")
def update(
    plugin_spec: str = typer.Argument(..., help="Plugin to update: name or name@version"),
) -> None:
    """Update an installed plugin to a newer version from the marketplace."""
    if "@" in plugin_spec:
        name, version = plugin_spec.split("@", 1)
    else:
        name, version = plugin_spec, None
    _do_update(name, version)


@app.command("update-all")
def update_all(
    check: bool = typer.Option(False, "--check", "-c", help="Only show available updates, do not install"),
) -> None:
    """Check for and apply updates for all installed plugins."""
    import asyncio
    from rich.table import Table
    from xcore.configurations.loader import ConfigLoader
    from xcore.marketplace import MarketplaceClient

    names = [p.name for p in _plugins_dir().iterdir() if p.is_dir() and not p.name.startswith("_")]
    if not names:
        console.print("[yellow]No installed plugins found.[/yellow]")
        return

    cfg = ConfigLoader.load(None)
    client = MarketplaceClient(cfg)

    async def _fetch_all():
        results = []
        for name in names:
            current = _installed_version(name)
            try:
                data = await client.get_plugin(name)
                latest = data.get("version", "?") if data else None
                url = data.get("download_url") if data else None
                src = data.get("source_type", "zip") if data else None
            except Exception:
                latest = url = src = None
            results.append((name, current, latest, url, src))
        return results

    with console.status("Checking marketplace for updates..."):
        results = asyncio.run(_fetch_all())

    table = Table(title="Plugin Update Status")
    table.add_column("Plugin", style="cyan")
    table.add_column("Installed", style="dim")
    table.add_column("Latest", style="magenta")
    table.add_column("Status", justify="center")

    upgradable = []
    for name, current, latest, url, src in results:
        if latest is None:
            status = "[dim]not on marketplace[/dim]"
        elif current == latest:
            status = "[green]up to date[/green]"
        else:
            status = "[yellow]update available[/yellow]"
            upgradable.append((name, current, latest, url, src))
        table.add_row(name, current or "?", latest or "—", status)

    console.print(table)

    if not upgradable:
        console.print("\n[green]All plugins are up to date.[/green]")
        return

    if check:
        console.print(f"\n[yellow]{len(upgradable)} update(s) available.[/yellow] Run without [dim]--check[/dim] to apply.")
        return

    import shutil
    from rich.prompt import Confirm
    from xcore.cli.plugin_cmd import handle_plugin

    names_str = ", ".join(f"[cyan]{n}[/cyan]" for n, *_ in upgradable)
    if not Confirm.ask(f"\nUpdate {names_str}?", default=True):
        return

    for name, current, latest, url, src in upgradable:
        console.print(f"\nUpdating [cyan]{name}[/cyan]: [dim]{current}[/dim] → [magenta]{latest}[/magenta]")
        plugin_path = _plugins_dir() / name
        if plugin_path.exists():
            shutil.rmtree(plugin_path)
        run(handle_plugin(ns(subcommand="install", name=name, source=src, url=url)))
        console.print(f"[green]✓[/green] {name} updated.")


# ── remove ────────────────────────────────────────────────────

@app.command("remove")
def remove(name: str) -> None:
    """Remove an installed plugin."""
    from xcore.cli.plugin_cmd import handle_plugin
    run(handle_plugin(ns(subcommand="remove", name=name)))


# ── info ──────────────────────────────────────────────────────

@app.command("info")
def info(name: str) -> None:
    """Show details of an installed plugin."""
    from xcore.cli.plugin_cmd import handle_plugin
    run(handle_plugin(ns(subcommand="info", name=name)))


# ── load / reload / unload / status / call ────────────────────

@app.command("load")
def load(name: str) -> None:
    """Load a plugin directly (boots xcore standalone)."""
    async def _run():
        from xcli._xcore import boot
        xcore = await boot()
        try:
            await xcore.plugins.load(name)
            console.print(f"[green]✓[/green] Plugin [cyan]{name}[/cyan] loaded.")
        finally:
            await xcore.plugins.shutdown()
    run(_run())


@app.command("reload")
def reload(name: str) -> None:
    """Reload a plugin directly (boots xcore standalone)."""
    async def _run():
        from xcli._xcore import boot
        xcore = await boot()
        try:
            await xcore.plugins.reload(name)
            console.print(f"[green]✓[/green] Plugin [cyan]{name}[/cyan] reloaded.")
        finally:
            await xcore.plugins.shutdown()
    run(_run())


@app.command("unload")
def unload(name: str) -> None:
    """Unload a plugin directly (boots xcore standalone)."""
    async def _run():
        from xcli._xcore import boot
        xcore = await boot()
        try:
            await xcore.plugins.unload(name)
            console.print(f"[green]✓[/green] Plugin [cyan]{name}[/cyan] unloaded.")
        finally:
            await xcore.plugins.shutdown()
    run(_run())


@app.command("status")
def status() -> None:
    """Show runtime status of all loaded plugins."""
    async def _run():
        from xcli._xcore import boot
        from rich.table import Table
        xcore = await boot()
        try:
            data = xcore.plugins.status()
            table = Table(title=f"Plugin Runtime Status ({data['count']} plugins)")
            table.add_column("Name", style="cyan")
            table.add_column("State", justify="center")
            table.add_column("Mode", style="green")
            for p in data["plugins"]:
                state = p.get("state", "?")
                color = "green" if state == "running" else "yellow"
                table.add_row(
                    p.get("name", "?"),
                    f"[{color}]{state}[/]",
                    p.get("mode", "?"),
                )
            console.print(table)
        finally:
            await xcore.plugins.shutdown()
    run(_run())


@app.command("call")
def call(
    name: str,
    action: str,
    payload: str = typer.Option("{}", "--payload", "-p", help="JSON payload"),
) -> None:
    """Call a plugin action directly (boots xcore standalone)."""
    import json
    async def _run():
        from xcli._xcore import boot
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid JSON payload:[/] {e}")
            raise typer.Exit(1)
        xcore = await boot()
        try:
            result = await xcore.plugins.call(name, action, data)
            console.print(result)
        finally:
            await xcore.plugins.shutdown()
    run(_run())


# ── marketplace ───────────────────────────────────────────────

@app.command("browse")
def browse() -> None:
    """List all plugins available on the marketplace."""
    from xcore.cli.marketplace_cmd import handle_marketplace
    run(handle_marketplace(ns(subcommand="list")))


@app.command("trending")
def trending() -> None:
    """Show trending plugins on the marketplace."""
    from xcore.cli.marketplace_cmd import handle_marketplace
    run(handle_marketplace(ns(subcommand="trending")))


@app.command("search")
def search(query: str) -> None:
    """Search the marketplace for a plugin."""
    from xcore.cli.marketplace_cmd import handle_marketplace
    run(handle_marketplace(ns(subcommand="search", query=query)))


@app.command("show")
def show(name: str) -> None:
    """Show marketplace details for a plugin (use info for installed plugins)."""
    from xcore.cli.marketplace_cmd import handle_marketplace
    run(handle_marketplace(ns(subcommand="show", name=name)))


@app.command("rate")
def rate(
    name: str,
    score: int = typer.Option(..., min=1, max=5, help="Score 1–5"),
) -> None:
    """Rate a marketplace plugin."""
    from xcore.cli.marketplace_cmd import handle_marketplace
    run(handle_marketplace(ns(subcommand="rate", name=name, score=score)))


# ── sign / verify / validate ──────────────────────────────────

@app.command("sign")
def sign(
    path: str,
    key: Optional[str] = typer.Option(None, "--key", "-k", help="HMAC signing key (reads from config if omitted)"),
) -> None:
    """Sign a plugin with its HMAC key."""
    from xcore.cli.plugin_cmd import handle_plugin
    run(handle_plugin(ns(subcommand="sign", path=path, key=key)))


@app.command("verify")
def verify(
    path: str,
    key: Optional[str] = typer.Option(None, "--key", "-k", help="HMAC signing key"),
) -> None:
    """Verify a plugin signature."""
    from xcore.cli.plugin_cmd import handle_plugin
    run(handle_plugin(ns(subcommand="verify", path=path, key=key)))


@app.command("validate")
def validate(path: str) -> None:
    """Validate a plugin manifest."""
    from xcore.cli.plugin_cmd import handle_plugin
    run(handle_plugin(ns(subcommand="validate", path=path)))
