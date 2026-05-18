"""
manager — Real-time monitoring and service lifecycle management.

Commands:
  top         Full-screen live dashboard (resources + logs)
  logs        Stream application logs (per-plugin filter, --follow)
  resources   CPU / memory / disk per plugin (--watch live table)
  metrics     Application metrics snapshot (boots xcore standalone)
  services    List all services with health status (--watch)
  reload      Reload (reconnect) a single service by name
  unload      Shutdown a single service by name
"""

from __future__ import annotations

import asyncio
import collections
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typer import Typer

_CTX = {"help_option_names": ["-h", "--help"]}
app = Typer(help="Runtime monitoring and service management.", context_settings=_CTX)
console = Console()
err = Console(stderr=True)


# ── config helpers ────────────────────────────────────────────

def _raw_cfg() -> dict:
    from xcli._xcore import load_raw_config
    return load_raw_config()


def _log_file() -> Path:
    cfg = _raw_cfg()
    p = cfg.get("observability", {}).get("logging", {}).get("file", "log/app.log")
    return Path(p)


def _plugins_root() -> Path:
    cfg = _raw_cfg()
    return Path(cfg.get("plugins", {}).get("directory", "./app"))


def _plugin_names() -> list[str]:
    d = _plugins_root()
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir() and not p.name.startswith("_"))


# ── logs ──────────────────────────────────────────────────────

def _print_log_line(line: str) -> None:
    if "ERROR" in line:
        console.print(f"[red]{escape(line)}[/red]")
    elif "WARNING" in line:
        console.print(f"[yellow]{escape(line)}[/yellow]")
    elif "DEBUG" in line:
        console.print(f"[dim]{escape(line)}[/dim]")
    else:
        console.print(escape(line))


@app.command("logs")
def logs(
    plugin: Optional[str] = typer.Argument(None, help="Filter by plugin name (substring)"),
    lines: int = typer.Option(50, "--lines", "-n", help="Initial lines to show"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Stream new log lines"),
) -> None:
    """Show application logs, optionally filtered by plugin name."""
    log_file = _log_file()
    if not log_file.exists():
        console.print(f"[yellow]⚠[/yellow] Log file not found: [cyan]{log_file}[/cyan]")
        console.print("[dim]Start the server first, or check observability.logging.file in integration.yaml[/dim]")
        raise typer.Exit(1)

    def _match(line: str) -> bool:
        return (not plugin) or plugin in line

    # Show last N matching lines
    all_lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in [l for l in all_lines if _match(l)][-lines:]:
        _print_log_line(line)

    if not follow:
        return

    label = f"plugin=[cyan]{plugin}[/cyan]" if plugin else "all"
    console.print(f"\n[dim]--- following {log_file} ({label}) — Ctrl+C to stop ---[/dim]")
    try:
        with open(log_file, encoding="utf-8", errors="replace") as fh:
            fh.seek(0, 2)  # jump to end
            while True:
                line = fh.readline()
                if line:
                    stripped = line.rstrip()
                    if _match(stripped):
                        _print_log_line(stripped)
                else:
                    time.sleep(0.1)
    except KeyboardInterrupt:
        pass


# ── resources ─────────────────────────────────────────────────

def _build_resources_table() -> Table:
    import psutil
    import yaml
    from xcore.kernel.sandbox.isolation import DiskWatcher

    plugins_root = _plugins_root()
    plugin_names = _plugin_names()

    # Find sandboxed worker subprocesses: python worker.py <plugin_dir>
    sandbox_pids: dict[str, psutil.Process] = {}
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmd = proc.info["cmdline"] or []
            if any("sandbox/worker.py" in str(c) for c in cmd):
                for name in plugin_names:
                    plugin_dir_str = str(plugins_root / name)
                    if any(plugin_dir_str in str(c) for c in cmd):
                        sandbox_pids[name] = proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    table = Table(title=f"Plugin Resources  [dim]{plugins_root}[/dim]", show_lines=True)
    table.add_column("Plugin", style="cyan", no_wrap=True)
    table.add_column("Mode", justify="center")
    table.add_column("PID", justify="right", style="dim")
    table.add_column("CPU %", justify="right", style="magenta")
    table.add_column("Mem MB", justify="right", style="magenta")
    table.add_column("Disk MB", justify="right", style="blue")
    table.add_column("Net Conn", justify="right", style="dim")
    table.add_column("State", justify="center")

    for name in plugin_names:
        plugin_dir = plugins_root / name
        manifest_path = plugin_dir / "plugin.yaml"

        mode = "?"
        max_disk = 100
        try:
            if manifest_path.exists():
                m = yaml.safe_load(manifest_path.read_text()) or {}
                mode = m.get("execution_mode", "?")[:9]
                max_disk = m.get("resources", {}).get("max_disk_mb", 100)
        except Exception:
            pass

        # Disk usage
        disk_str = "?"
        try:
            dw = DiskWatcher(plugin_dir / "data", max_disk)
            s = dw.stats()
            color = "red" if not s["ok"] else "blue"
            disk_str = f"[{color}]{s['used_mb']}/{s['max_mb']}[/{color}]"
        except Exception:
            pass

        proc = sandbox_pids.get(name)
        pid_str = cpu_str = mem_str = conn_str = "—"
        state_str = "[dim]in-process[/dim]"

        if proc:
            try:
                pid_str = str(proc.pid)
                cpu = proc.cpu_percent(interval=0.05)
                cpu_color = "red" if cpu > 80 else ("yellow" if cpu > 40 else "green")
                cpu_str = f"[{cpu_color}]{cpu:.1f}[/{cpu_color}]"

                mem = proc.memory_info().rss / 1024 ** 2
                mem_color = "red" if mem > 400 else ("yellow" if mem > 200 else "magenta")
                mem_str = f"[{mem_color}]{mem:.1f}[/{mem_color}]"

                try:
                    conn_str = str(len(proc.net_connections()))
                except (psutil.AccessDenied, AttributeError):
                    conn_str = "?"

                state = proc.status()
                state_str = "[green]running[/green]" if state == "running" else f"[yellow]{state}[/yellow]"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                state_str = "[red]gone[/red]"

        table.add_row(name, mode, pid_str, cpu_str, mem_str, disk_str, conn_str, state_str)

    return table


@app.command("resources")
def resources(
    watch: bool = typer.Option(False, "--watch", "-w", help="Live refresh every second"),
) -> None:
    """Show CPU, memory, disk and network usage per plugin."""
    try:
        import psutil  # noqa: F401
    except ImportError:
        err.print("[red]psutil required — run: uv add psutil[/red]")
        raise typer.Exit(1)

    if not watch:
        console.print(_build_resources_table())
        return

    console.print("[dim]Ctrl+C to stop[/dim]")
    try:
        with Live(console=console, refresh_per_second=2) as live:
            while True:
                live.update(_build_resources_table())
                time.sleep(1)
    except KeyboardInterrupt:
        pass


# ── metrics ───────────────────────────────────────────────────

@app.command("metrics")
def metrics(
    watch: bool = typer.Option(False, "--watch", "-w", help="Live refresh (boots xcore once)"),
) -> None:
    """Show application metrics snapshot (boots xcore standalone)."""
    async def _fetch_metrics():
        from xcli._xcore import boot
        xcore = await boot()
        try:
            return xcore.metrics.snapshot()
        finally:
            await xcore.plugins.shutdown()

    snap = asyncio.run(_fetch_metrics())

    def _render_snap(s: dict) -> Panel:
        from rich.console import Group

        parts: list = []
        if s.get("counters"):
            t = Table(title="Counters", box=None, show_header=True, padding=(0, 2))
            t.add_column("Metric", style="cyan")
            t.add_column("Value", justify="right", style="magenta")
            for k, v in sorted(s["counters"].items()):
                t.add_row(escape(k), str(v))
            parts.append(t)

        if s.get("gauges"):
            t = Table(title="Gauges", box=None, show_header=True, padding=(0, 2))
            t.add_column("Metric", style="cyan")
            t.add_column("Value", justify="right", style="green")
            for k, v in sorted(s["gauges"].items()):
                t.add_row(escape(k), f"{v:.4g}")
            parts.append(t)

        if s.get("histograms"):
            t = Table(title="Histograms", box=None, show_header=True, padding=(0, 2))
            t.add_column("Metric", style="cyan")
            t.add_column("Count", justify="right")
            t.add_column("Sum", justify="right", style="magenta")
            t.add_column("Mean", justify="right", style="green")
            for k, v in sorted(s["histograms"].items()):
                t.add_row(escape(k), str(v["count"]), f"{v['sum']:.4f}", f"{v['mean']:.4f}")
            parts.append(t)

        if not parts:
            return Panel("[yellow]No metrics recorded yet.[/yellow]", title="Metrics")
        return Panel(Group(*parts), title="Application Metrics", border_style="cyan")

    if not watch:
        console.print(_render_snap(snap))
        return

    # Watch: re-fetch every 2s (re-boots xcore each time — only for dev use)
    console.print("[dim]Re-fetching metrics every 2s — Ctrl+C to stop[/dim]")
    try:
        with Live(console=console, refresh_per_second=1) as live:
            while True:
                try:
                    s = asyncio.run(_fetch_metrics())
                    live.update(_render_snap(s))
                except Exception as e:
                    live.update(Panel(f"[red]{escape(str(e))}[/red]", title="Metrics Error"))
                time.sleep(2)
    except KeyboardInterrupt:
        pass


# ── services list ─────────────────────────────────────────────

async def _fetch_services() -> tuple[dict, dict]:
    from xcore.configurations.loader import ConfigLoader
    from xcore.services import ServiceContainer

    cfg = ConfigLoader.load(None)
    container = ServiceContainer(cfg.services)
    container.load_default_providers()
    await container.init()
    health = await container.health()
    status = container.status()
    await container.shutdown()
    return health, status


def _build_services_table() -> Table:
    health, status = asyncio.run(_fetch_services())

    table = Table(title="Services Status", show_lines=False)
    table.add_column("Service", style="cyan", no_wrap=True)
    table.add_column("Status", justify="center")
    table.add_column("Health", justify="center")
    table.add_column("Details", style="dim")

    for svc_id, svc_info in status["services"].items():
        st = svc_info.get("status", "?")
        if st == "ready":
            state_cell = "[green]ready[/green]"
        elif st in ("initializing", "uninitialized"):
            state_cell = f"[yellow]{st}[/yellow]"
        else:
            state_cell = f"[red]{st}[/red]"

        h = health["services"].get(svc_id, {})
        ok = h.get("ok", None)
        health_sym = "✅" if ok else ("❌" if ok is False else "—")
        health_msg = h.get("msg", "")

        details = {k: v for k, v in svc_info.items() if k not in ("name", "status")}
        details_str = escape(", ".join(f"{k}={v}" for k, v in details.items()))
        if health_msg and not ok:
            details_str = f"[red]{escape(health_msg)}[/red]"

        table.add_row(svc_info.get("name", svc_id), state_cell, health_sym, details_str)

    # Also show registered service keys
    keys = ", ".join(sorted(status.get("registered_keys", [])))
    if keys:
        table.caption = f"[dim]Keys: {escape(keys)}[/dim]"

    return table


@app.command("services")
def services_cmd(
    watch: bool = typer.Option(False, "--watch", "-w", help="Live refresh every 3s"),
) -> None:
    """List all services with status and health checks."""
    if not watch:
        try:
            console.print(_build_services_table())
        except Exception as e:
            err.print(f"[red]Error fetching services:[/red] {escape(str(e))}")
            raise typer.Exit(1)
        return

    console.print("[dim]Refreshing every 3s — Ctrl+C to stop[/dim]")
    try:
        with Live(console=console, refresh_per_second=0.5) as live:
            while True:
                try:
                    live.update(_build_services_table())
                except Exception as e:
                    live.update(Panel(f"[red]{escape(str(e))}[/red]", title="Services Error"))
                time.sleep(3)
    except KeyboardInterrupt:
        pass


# ── service reload ────────────────────────────────────────────

@app.command("reload")
def service_reload(name: str = typer.Argument(..., help="Service name (e.g. database, cache, scheduler)")) -> None:
    """Reload (shutdown then re-init) a specific service."""
    async def _reload():
        from xcore.configurations.loader import ConfigLoader
        from xcore.services import ServiceContainer

        cfg = ConfigLoader.load(None)
        container = ServiceContainer(cfg.services)
        container.load_default_providers()
        await container.init()

        # Try exact name then <name>_service
        svc = container._services.get(name) or container._services.get(f"{name}_service")
        if svc is None:
            available = sorted(container._services.keys())
            err.print(f"[red]Service '[cyan]{name}[/cyan]' not found.[/red]")
            err.print(f"Available managed services: {', '.join(available) or 'none'}")
            err.print(f"Registered keys: {', '.join(sorted(container.status()['registered_keys']))}")
            await container.shutdown()
            raise typer.Exit(1)

        svc_label = f"[cyan]{name}[/cyan]"
        with console.status(f"Reloading {svc_label}..."):
            await svc.shutdown()
            await svc.init()
            ok, msg = await svc.health_check()

        sym = "[green]✓[/green]" if ok else "[red]✗[/red]"
        console.print(f"{sym} Service {svc_label} reloaded — {escape(msg)}")

        # Shutdown the rest cleanly
        await container.shutdown()

    asyncio.run(_reload())


# ── service unload ────────────────────────────────────────────

@app.command("unload")
def service_unload(name: str = typer.Argument(..., help="Service name to stop")) -> None:
    """Shutdown a specific service (unload it from the container)."""
    async def _unload():
        from xcore.configurations.loader import ConfigLoader
        from xcore.services import ServiceContainer

        cfg = ConfigLoader.load(None)
        container = ServiceContainer(cfg.services)
        container.load_default_providers()
        await container.init()

        svc = container._services.get(name) or container._services.get(f"{name}_service")
        if svc is None:
            available = sorted(container._services.keys())
            err.print(f"[red]Service '[cyan]{name}[/cyan]' not a managed service.[/red]")
            err.print(f"Available: {', '.join(available) or 'none'}")
            await container.shutdown()
            raise typer.Exit(1)

        with console.status(f"Stopping [cyan]{name}[/cyan]..."):
            await svc.shutdown()

        console.print(f"[green]✓[/green] Service [cyan]{name}[/cyan] unloaded.")

        # Stop remaining services cleanly
        for key, other in reversed(list(container._services.items())):
            if key not in (name, f"{name}_service"):
                try:
                    await other.shutdown()
                except Exception:
                    pass

    asyncio.run(_unload())


# ── top ───────────────────────────────────────────────────────

@app.command("top")
def top(
    log_lines: int = typer.Option(12, "--log-lines", "-n", help="Log lines shown in the bottom panel"),
    interval: float = typer.Option(1.0, "--interval", "-i", help="Refresh interval in seconds"),
) -> None:
    """Full-screen live dashboard: plugin resources (top) + live logs (bottom)."""
    try:
        import psutil  # noqa: F401
    except ImportError:
        err.print("[red]psutil required — run: uv add psutil[/red]")
        raise typer.Exit(1)

    log_file = _log_file()
    log_ring: collections.deque[str] = collections.deque(maxlen=log_lines)

    # Seed ring with last N lines from the log file
    if log_file.exists():
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-log_lines:]:
            log_ring.append(line)

    def _log_panel() -> Panel:
        text = Text()
        for line in log_ring:
            if "ERROR" in line:
                text.append(line + "\n", style="red")
            elif "WARNING" in line:
                text.append(line + "\n", style="yellow")
            elif "DEBUG" in line:
                text.append(line + "\n", style="dim")
            else:
                text.append(line + "\n")
        return Panel(text, title=f"[bold]Logs[/bold]  [dim]{log_file}[/dim]", border_style="blue")

    def _tick_logs(fh) -> None:
        while True:
            line = fh.readline()
            if not line:
                break
            log_ring.append(line.rstrip())

    layout = Layout()
    layout.split_column(
        Layout(name="resources", ratio=3),
        Layout(name="logs", ratio=2),
    )

    console.print("[dim]xcli manager top — Ctrl+C to quit[/dim]")

    log_fh = None
    try:
        if log_file.exists():
            log_fh = open(log_file, encoding="utf-8", errors="replace")
            log_fh.seek(0, 2)

        with Live(layout, console=console, refresh_per_second=int(1 / interval) + 1, screen=True):
            while True:
                # Resources panel
                try:
                    layout["resources"].update(
                        Panel(_build_resources_table(), title="[bold]Plugin Resources[/bold]", border_style="cyan")
                    )
                except Exception as e:
                    layout["resources"].update(Panel(f"[red]{escape(str(e))}[/red]", title="Resources Error"))

                # Log panel — drain new lines from file
                if log_fh:
                    _tick_logs(log_fh)
                elif log_file.exists():
                    log_fh = open(log_file, encoding="utf-8", errors="replace")
                    log_fh.seek(0, 2)

                layout["logs"].update(_log_panel())
                time.sleep(interval)

    except KeyboardInterrupt:
        pass
    finally:
        if log_fh:
            log_fh.close()
