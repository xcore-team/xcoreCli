import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from typer import Typer

from xcli._run import ns, run

_CTX = {"help_option_names": ["-h", "--help"]}
app = Typer(help="Sandbox inspection and runtime.", context_settings=_CTX)
console = Console()
err = Console(stderr=True)


# ── run ───────────────────────────────────────────────────────

@app.command("run")
def sandbox_run(name: str) -> None:
    """Launch a plugin in an isolated sandbox."""
    from xcore.cli.sandbox_cmd import handle_sandbox
    run(handle_sandbox(ns(subcommand="run", name=name)))


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
        from xcore.configurations.loader import ConfigLoader
        from xcore.kernel.sandbox.process_manager import SandboxConfig, SandboxProcessManager
        from xcore.kernel.security.validation import ManifestValidator
        from xcli._xcore import _NullCtx

        cfg = ConfigLoader.load(None)
        plugin_dir = Path(cfg.plugins.directory) / name

        if not plugin_dir.is_dir():
            err.print(f"[red]Plugin '[cyan]{name}[/cyan]' not found in {cfg.plugins.directory}[/red]")
            raise typer.Exit(1)

        try:
            manifest, _, _ = ManifestValidator().load_and_validate(plugin_dir)
        except Exception as e:
            err.print(f"[red]Invalid manifest:[/red] {escape(str(e))}")
            raise typer.Exit(1)

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
    from xcore.cli.sandbox_cmd import handle_sandbox
    run(handle_sandbox(ns(subcommand="limits", name=name)))


@app.command("network")
def network(name: str) -> None:
    """Show the network policy for a plugin."""
    from xcore.cli.sandbox_cmd import handle_sandbox
    run(handle_sandbox(ns(subcommand="network", name=name)))


@app.command("fs")
def fs(name: str) -> None:
    """Show the filesystem policy for a plugin."""
    from xcore.cli.sandbox_cmd import handle_sandbox
    run(handle_sandbox(ns(subcommand="fs", name=name)))
