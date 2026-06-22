from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.markup import escape
from typer import Typer

from .shared import console


# ── Helpers ────────────────────────────────────────────────────


def _default_schema_path(plugin_path: Path) -> Path:
    """Returns .xcore/schemas/<plugin_name>.json next to the plugin directory."""
    root = plugin_path.parent.parent  # app/ → project root
    return root / '.xcore' / 'schemas' / f'{plugin_path.name}.json'


def _import_plugin_class(plugin_path: Path):
    """
    Dynamically imports the Plugin class from <plugin_path>/src/main.py.
    Returns the class or None if import fails.
    """
    entry = plugin_path / 'src' / 'main.py'
    if not entry.exists():
        entry = plugin_path / 'main.py'
    if not entry.exists():
        return None, f'Entry point not found (tried src/main.py and main.py)'

    src_dir = str(entry.parent)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    spec = importlib.util.spec_from_file_location('_xcli_plugin_tmp', entry)
    if spec is None or spec.loader is None:
        return None, 'Cannot load module spec'
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    except Exception as exc:
        return None, str(exc)

    cls = getattr(mod, 'Plugin', None)
    if cls is None:
        return None, 'No Plugin class found in module'
    return cls, None


def _extract_ipc_schemas(plugin_name: str, plugin_cls) -> list[dict]:
    """
    Inspects Plugin class methods for @action + @schema decorators.
    Returns a list of ActionSchema-compatible dicts.
    """
    schemas = []
    for attr_name in dir(plugin_cls):
        method = getattr(plugin_cls, attr_name, None)
        if not callable(method):
            continue
        action_name = getattr(method, '_xcore_action', None)
        schema_info = getattr(method, '_xcore_schema', None)
        if action_name is None:
            continue
        entry: dict = {
            'plugin': plugin_name,
            'action': action_name,
            'version': '0.0.0',
            'input': {},
            'output': {},
            'deprecated_fields': {},
            'breaking_since': None,
            'description': '',
        }
        if schema_info:
            entry['version'] = schema_info.get('version', '0.0.0')
            entry['input'] = schema_info.get('input', {})
            entry['output'] = schema_info.get('output', {})
            entry['deprecated_fields'] = schema_info.get('deprecated_fields', {})
            entry['breaking_since'] = schema_info.get('breaking_since')
            entry['description'] = schema_info.get('description', '')
        schemas.append(entry)
    return schemas


def _extract_event_subscriptions(plugin_cls) -> list[dict]:
    """
    Inspects Plugin class methods for @on_event decorators.
    Returns a list of {event, method, priority, once} dicts.
    """
    subs = []
    for attr_name in dir(plugin_cls):
        method = getattr(plugin_cls, attr_name, None)
        if not callable(method):
            continue
        event_name = getattr(method, '_xcore_event', None)
        if event_name is None:
            continue
        subs.append({
            'event': event_name,
            'method': attr_name,
            'priority': getattr(method, '_xcore_event_priority', 50),
            'once': getattr(method, '_xcore_event_once', False),
        })
    return subs


def register(app: Typer) -> None:
    @app.command('sign')
    def sign(
        path: str,
        key: Optional[str] = typer.Option(None, '--key', '-k', help='HMAC signing key (reads from config if omitted)'),
    ) -> None:
        """Sign a plugin with its HMAC key."""
        from xcli._xcore import _require_xcore
        _require_xcore()
        from xcore.kernel.security.signature import sign_plugin
        from xcore.kernel.security.validation import ManifestValidator

        plugin_path = Path(path)
        secret = (key or 'change-me').encode()
        try:
            manifest, _, _ = ManifestValidator().load_and_validate(plugin_path)
            signature = sign_plugin(manifest, secret)
            console.print(f'[green]✓[/green] Signed: [dim]{signature}[/dim]')
        except Exception as e:
            console.print(f'[red]Sign failed:[/red] {escape(str(e))}')
            raise typer.Exit(1)

    @app.command('verify')
    def verify(
        path: str,
        key: Optional[str] = typer.Option(None, '--key', '-k', help='HMAC signing key'),
    ) -> None:
        """Verify a plugin signature."""
        from xcli._xcore import _require_xcore
        _require_xcore()
        from xcore.kernel.security.signature import SignatureError, verify_plugin
        from xcore.kernel.security.validation import ManifestValidator

        plugin_path = Path(path)
        secret = (key or 'change-me').encode()
        try:
            manifest, _, _ = ManifestValidator().load_and_validate(plugin_path)
            verify_plugin(manifest, secret)
            console.print(f'[green]✓[/green] Signature valid: [cyan]{manifest.name}[/cyan]')
        except SignatureError as e:
            console.print(f'[red]✗ Invalid signature:[/red] {escape(str(e))}')
            raise typer.Exit(1)
        except Exception as e:
            console.print(f'[red]Error:[/red] {escape(str(e))}')
            raise typer.Exit(1)

    @app.command('validate')
    def validate(
        path: str,
        check_breaking: bool = typer.Option(
            False, '--check-breaking',
            help='Compare current IPC actions & events against saved snapshot and report breaking changes.',
        ),
        save: bool = typer.Option(
            False, '--save',
            help='Save current IPC action schemas and event subscriptions to the snapshot file.',
        ),
        schema_file: Optional[str] = typer.Option(
            None, '--schema-file', '-s',
            help='Path to the schemas JSON snapshot (default: .xcore/schemas/<plugin>.json).',
        ),
    ) -> None:
        """Validate a plugin manifest, and optionally save or check IPC action / event schemas."""
        from xcli._xcore import _require_xcore
        _require_xcore()
        from xcore.kernel.security.validation import ManifestValidator

        plugin_path = Path(path).resolve()
        try:
            manifest, _, _ = ManifestValidator().load_and_validate(plugin_path)
            console.print(
                f'[green]✓[/green] Valid manifest: [cyan]{manifest.name}[/cyan] '
                f'v{manifest.version} [{manifest.execution_mode.value}]'
            )
        except Exception as e:
            console.print(f'[red]✗ Invalid manifest:[/red] {escape(str(e))}')
            raise typer.Exit(1)

        if not save and not check_breaking:
            return

        # ── Load plugin class for schema inspection ───────────────
        plugin_cls, err = _import_plugin_class(plugin_path)
        if plugin_cls is None:
            console.print(f'[yellow]⚠ Cannot inspect plugin source:[/yellow] {err}')
            console.print('[dim]  Schema extraction requires importable src/main.py.[/dim]')
            raise typer.Exit(1)

        plugin_name = manifest.name
        ipc_schemas = _extract_ipc_schemas(plugin_name, plugin_cls)
        event_subs  = _extract_event_subscriptions(plugin_cls)

        snap_path = Path(schema_file).resolve() if schema_file else _default_schema_path(plugin_path)

        # ── --save ────────────────────────────────────────────────
        if save:
            from xcore.kernel.schema import ActionSchema, SchemaRegistry

            registry = SchemaRegistry()
            for s in ipc_schemas:
                registry.register(ActionSchema(**s))

            snap_path.parent.mkdir(parents=True, exist_ok=True)
            data = {key: s.to_dict() for key, s in registry._schemas.items()}  # noqa: SLF001
            # Attach event subscriptions as metadata (not part of SchemaRegistry)
            snapshot = {'actions': data, 'events': event_subs}
            snap_path.write_text(json.dumps(snapshot, indent=2), encoding='utf-8')

            console.print(f'\n[green]✓[/green] Schemas saved → [dim]{snap_path}[/dim]')
            if ipc_schemas:
                from rich.table import Table
                t = Table(title=f'IPC Actions ({len(ipc_schemas)})', show_header=True)
                t.add_column('Action', style='cyan')
                t.add_column('Version', style='magenta')
                t.add_column('Input fields', style='dim')
                t.add_column('Output fields', style='dim')
                for s in sorted(ipc_schemas, key=lambda x: x['action']):
                    t.add_row(
                        s['action'], s['version'],
                        ', '.join(s['input']) or '—',
                        ', '.join(s['output']) or '—',
                    )
                console.print(t)
            else:
                console.print('[yellow]  No @action-decorated methods found.[/yellow]')

            if event_subs:
                from rich.table import Table
                t = Table(title=f'Event Subscriptions ({len(event_subs)})', show_header=True)
                t.add_column('Event', style='cyan')
                t.add_column('Method', style='dim')
                t.add_column('Priority', style='magenta')
                for e in sorted(event_subs, key=lambda x: x['event']):
                    t.add_row(e['event'], e['method'], str(e['priority']))
                console.print(t)
            else:
                console.print('[dim]  No @on_event-decorated methods found.[/dim]')

        # ── --check-breaking ──────────────────────────────────────
        if check_breaking:
            from xcore.kernel.schema import ActionSchema, BreakingChangeDetector, SchemaRegistry

            if not snap_path.exists():
                console.print(
                    f'[yellow]⚠ No snapshot found at [dim]{snap_path}[/dim].\n'
                    f'  Run [cyan]xcli plugin security validate {path} --save[/cyan] first.[/yellow]'
                )
                raise typer.Exit(1)

            raw_snap = json.loads(snap_path.read_text(encoding='utf-8'))
            # Support both old format (flat dict) and new format ({actions, events})
            prev_actions = raw_snap.get('actions', raw_snap) if isinstance(raw_snap, dict) else {}
            prev_events  = raw_snap.get('events', []) if isinstance(raw_snap, dict) else []

            previous = SchemaRegistry()
            for key, d in prev_actions.items():
                try:
                    previous._schemas[key] = ActionSchema.from_dict(d)  # noqa: SLF001
                except Exception:
                    pass

            current = SchemaRegistry()
            for s in ipc_schemas:
                current.register(ActionSchema(**s))

            detector = BreakingChangeDetector(previous, current, plugin_filter=plugin_name)
            breaking = detector.detect()

            console.print()
            if breaking:
                console.print(f'[red bold]✗ {len(breaking)} breaking change(s) detected:[/red bold]')
                for change in breaking:
                    console.print(f'[red]  {escape(str(change))}[/red]')
                raise typer.Exit(1)
            else:
                console.print(f'[green]✓[/green] No breaking IPC changes detected for [cyan]{plugin_name}[/cyan].')

            # Event subscription diff (informational, not an error)
            prev_event_names = {e['event'] for e in prev_events}
            curr_event_names = {e['event'] for e in event_subs}
            removed_events = prev_event_names - curr_event_names
            added_events   = curr_event_names - prev_event_names
            if removed_events:
                console.print('[yellow]  Event subscriptions removed:[/yellow]')
                for ev in sorted(removed_events):
                    console.print(f'[yellow]    - {escape(ev)}[/yellow]')
            if added_events:
                console.print('[dim]  Event subscriptions added:[/dim]')
                for ev in sorted(added_events):
                    console.print(f'[dim]    + {ev}[/dim]')
