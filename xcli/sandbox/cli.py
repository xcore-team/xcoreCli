import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from typer import Typer

from xcli._run import run

_CTX = {"help_option_names": ["-h", "--help"]}
app = Typer(help="Sandbox inspection and runtime.", context_settings=_CTX)
console = Console()
err = Console(stderr=True)


def _load_manifest(name: str):
    from xcore.configurations.loader import ConfigLoader
    from xcore.kernel.security.validation import ManifestValidator

    cfg = ConfigLoader.load(None)
    plugin_dir = Path(cfg.plugins.directory) / name
    if not plugin_dir.is_dir():
        err.print(f"[red]Plugin '[cyan]{name}[/cyan]' not found.[/red]")
        raise typer.Exit(1)
    try:
        manifest, _, _ = ManifestValidator().load_and_validate(plugin_dir)
        return manifest, plugin_dir
    except Exception as e:
        err.print(f"[red]Invalid manifest:[/red] {escape(str(e))}")
        raise typer.Exit(1)


# ── run ───────────────────────────────────────────────────────

@app.command("run")
def sandbox_run(name: str) -> None:
    """Launch a plugin in an isolated sandbox and keep it running."""
    async def _run():
        from xcore.kernel.sandbox.process_manager import SandboxConfig, SandboxProcessManager
        from xcli._xcore import _NullCtx

        manifest, _ = _load_manifest(name)
        config = SandboxConfig(
            timeout=manifest.resources.timeout_seconds,
            max_restarts=3,
            startup_timeout=10.0,
        )
        mgr = SandboxProcessManager(manifest, _NullCtx(), config)
        try:
            with console.status(f"Starting sandbox [cyan]{name}[/cyan]..."):
                await mgr.start()
            console.print(f"[green]✓[/green] Sandbox [cyan]{name}[/cyan] running — Ctrl+C to stop.")
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            await mgr.stop()
            console.print(f"[dim]Sandbox {name} stopped.[/dim]")

    run(_run())


# ── call ──────────────────────────────────────────────────────

@app.command("call")
def sandbox_call(
    name: str,
    action: str,
    payload: str = typer.Option("{}", "--payload", "-p", help="JSON payload"),
) -> None:
    """Start a plugin sandbox, call one action, print the result, then stop."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        err.print(f"[red]Invalid JSON payload:[/red] {e}")
        raise typer.Exit(1)

    async def _run():
        from xcore.kernel.sandbox.process_manager import SandboxConfig, SandboxProcessManager
        from xcli._xcore import _NullCtx

        manifest, plugin_dir = _load_manifest(name)

        if manifest.execution_mode.value != "sandboxed":
            err.print(
                f"[yellow]⚠[/yellow] Plugin '[cyan]{name}[/cyan]' is mode "
                f"[magenta]{manifest.execution_mode.value}[/magenta], not sandboxed. "
                f"Use [dim]xcli plugin call[/dim] instead."
            )
            raise typer.Exit(1)

        config = SandboxConfig(
            timeout=manifest.resources.timeout_seconds,
            max_restarts=0,
            startup_timeout=5.0,
        )
        mgr = SandboxProcessManager(manifest, _NullCtx(), config)

        try:
            with console.status(f"Starting sandbox [cyan]{name}[/cyan]..."):
                await mgr.start()

            console.print(f"[dim]→ {name}.{action}({payload})[/dim]")
            resp = await mgr._channel.call(action, data)

            if resp.success:
                console.print(Panel(
                    json.dumps(resp.data, indent=2, ensure_ascii=False),
                    title=f"[green]{name}.{action}[/green]",
                    border_style="green",
                ))
            else:
                console.print(Panel(
                    escape(str(resp.data)),
                    title=f"[red]{name}.{action} — error[/red]",
                    border_style="red",
                ))
        finally:
            await mgr.stop()
            console.print(f"[dim]Sandbox {name} stopped.[/dim]")

    run(_run())


# ── limits / network / fs ─────────────────────────────────────

@app.command("limits")
def limits(name: str) -> None:
    """Show resource limits declared in the plugin manifest."""
    manifest, _ = _load_manifest(name)
    r = manifest.resources

    table = Table(title=f"Resource Limits — {name}", show_header=False, min_width=40)
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="magenta")
    table.add_row("timeout", f"{r.timeout_seconds}s")
    table.add_row("max_memory_mb", f"{r.max_memory_mb} MB")
    table.add_row("max_disk_mb", f"{r.max_disk_mb} MB")
    table.add_row("rate_limit", f"{r.rate_limit.calls} calls / {r.rate_limit.period_seconds}s")
    console.print(table)


@app.command("network")
def network(name: str) -> None:
    """Show the network policy for a plugin."""
    import yaml

    manifest, plugin_dir = _load_manifest(name)

    # Try manifest attribute first, fall back to raw yaml
    raw_network = getattr(manifest, "network", None)
    if raw_network is None:
        manifest_path = plugin_dir / "plugin.yaml"
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        raw_network = raw.get("network", {})

    if not raw_network:
        console.print(f"[dim]No network policy declared for [cyan]{name}[/cyan].[/dim]")
        return

    table = Table(title=f"Network Policy — {name}", show_header=False)
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="magenta")
    if isinstance(raw_network, dict):
        for k, v in raw_network.items():
            table.add_row(str(k), str(v))
    else:
        table.add_row("policy", escape(str(raw_network)))
    console.print(table)


@app.command("fs")
def fs(name: str) -> None:
    """Show the filesystem policy for a plugin."""
    import yaml

    manifest, plugin_dir = _load_manifest(name)

    raw_fs = getattr(manifest, "filesystem", None)
    if raw_fs is None:
        manifest_path = plugin_dir / "plugin.yaml"
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        raw_fs = raw.get("filesystem", {})

    if not raw_fs:
        console.print(f"[dim]No filesystem policy declared for [cyan]{name}[/cyan].[/dim]")
        return

    table = Table(title=f"Filesystem Policy — {name}", show_header=False)
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="magenta")
    if isinstance(raw_fs, dict):
        for k, v in raw_fs.items():
            table.add_row(str(k), str(v))
    else:
        table.add_row("policy", escape(str(raw_fs)))
    console.print(table)
