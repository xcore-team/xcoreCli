from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Optional

import typer
from rich.markup import escape
from typer import Typer

from .shared import console


# ── AST-based schema extraction (no import needed) ─────────────


def _ast_value(node: ast.expr) -> object:
    """Convert a simple AST literal/name to a Python value."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f'{_ast_value(node.value)}.{node.attr}'
    if isinstance(node, ast.Tuple):
        elts = [_ast_value(e) for e in node.elts]
        return elts[0] if elts else 'Any'
    if isinstance(node, ast.Dict):
        result = {}
        for k, v in zip(node.keys, node.values):
            if k is not None:
                key = _ast_value(k)
                val = _ast_value(v)
                result[str(key)] = str(val) if val is not None else 'Any'
        return result
    if isinstance(node, ast.List):
        return [_ast_value(e) for e in node.elts]
    return 'Any'


def _decorator_name(dec: ast.expr) -> str:
    """Return the base name of a decorator (strips call, attributes)."""
    if isinstance(dec, ast.Call):
        return _decorator_name(dec.func)
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        return dec.attr
    return ''


def _extract_from_source(plugin_name: str, source_path: Path) -> tuple[list[dict], list[dict]]:
    """
    Parse a plugin source file with AST and extract:
      - IPC action schemas  (decorated with @action + optional @schema)
      - Event subscriptions (decorated with @on_event)

    Returns (ipc_schemas, event_subs).
    """
    try:
        tree = ast.parse(source_path.read_text(encoding='utf-8'), filename=str(source_path))
    except SyntaxError as exc:
        raise ValueError(f'Syntax error in {source_path}: {exc}') from exc

    ipc_schemas: list[dict] = []
    event_subs: list[dict] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            action_name: str | None = None
            schema_info: dict | None = None
            event_name: str | None = None
            event_priority: int = 50
            event_once: bool = False

            for dec in item.decorator_list:
                name = _decorator_name(dec)

                if name == 'action' and isinstance(dec, ast.Call) and dec.args:
                    action_name = str(_ast_value(dec.args[0]))

                elif name == 'schema' and isinstance(dec, ast.Call):
                    kw = {k.arg: _ast_value(k.value) for k in dec.keywords if k.arg}
                    raw_in = kw.get('input') or {}
                    raw_out = kw.get('output') or {}
                    schema_info = {
                        'version': str(kw.get('version', '0.0.0')),
                        'input': raw_in if isinstance(raw_in, dict) else {},
                        'output': raw_out if isinstance(raw_out, dict) else {},
                        'deprecated_fields': kw.get('deprecated_fields') or {},
                        'breaking_since': kw.get('breaking_since'),
                        'description': str(kw.get('description', '')),
                    }

                elif name == 'on_event' and isinstance(dec, ast.Call) and dec.args:
                    event_name = str(_ast_value(dec.args[0]))
                    kws = {k.arg: _ast_value(k.value) for k in dec.keywords if k.arg}
                    event_priority = int(kws.get('priority', 50))
                    event_once = bool(kws.get('once', False))

            if action_name is not None:
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
                    entry.update(schema_info)
                ipc_schemas.append(entry)

            if event_name is not None:
                event_subs.append({
                    'event': event_name,
                    'method': item.name,
                    'priority': event_priority,
                    'once': event_once,
                })

    return ipc_schemas, event_subs


def _find_entry_point(plugin_path: Path, entry_point: str = 'src/main.py') -> Path | None:
    """Locate the plugin entry point file."""
    candidates = [
        plugin_path / entry_point,
        plugin_path / 'src' / 'main.py',
        plugin_path / 'main.py',
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _default_schema_path(project_root: Path) -> Path:
    return project_root / '.xcore' / 'schemas.json'


# ── Single-plugin validation helper ────────────────────────────


def _validate_one(plugin_path: Path, manifest_validator) -> tuple[object | None, str | None]:
    """Validate manifest of a single plugin. Returns (manifest, error_msg)."""
    try:
        manifest, _, _ = manifest_validator.load_and_validate(plugin_path)
        return manifest, None
    except Exception as exc:
        return None, str(exc)


# ── Command registration ────────────────────────────────────────


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
        path: Optional[str] = typer.Argument(
            None,
            help='Plugin directory to validate. Omit to scan all plugins from integration.yaml.',
        ),
        check_breaking: bool = typer.Option(
            False, '--check-breaking',
            help='Compare IPC actions & events against saved snapshot and report breaking changes.',
        ),
        save: bool = typer.Option(
            False, '--save',
            help='Save IPC action schemas and event subscriptions to the snapshot file.',
        ),
        schema_file: Optional[str] = typer.Option(
            None, '--schema-file', '-s',
            help='Path to the schemas JSON snapshot (default: .xcore/schemas.json).',
        ),
    ) -> None:
        """
        Validate plugin manifest(s) and optionally save or diff IPC action / event schemas.

        Without a PATH, reads integration.yaml to find the plugins directory
        and validates every plugin found there.
        """
        from xcli._xcore import _require_xcore
        _require_xcore()
        from xcore.kernel.security.validation import ManifestValidator

        validator = ManifestValidator()

        # ── Resolve the list of plugins to process ────────────────
        if path:
            plugin_dirs = [Path(path).resolve()]
            project_root = plugin_dirs[0].parent.parent
        else:
            from xcli.config.runtime import find_config_path, plugins_directory
            cfg_path = find_config_path(required=True)
            assert cfg_path is not None
            project_root = cfg_path.parent.resolve()
            plugins_root = plugins_directory()
            if not plugins_root.exists():
                console.print(f'[yellow]Plugins directory not found:[/yellow] {plugins_root}')
                raise typer.Exit(1)
            plugin_dirs = sorted(
                d for d in plugins_root.iterdir()
                if d.is_dir() and not d.name.startswith('_')
            )
            if not plugin_dirs:
                console.print('[yellow]No plugins found.[/yellow]')
                return

        snap_path = Path(schema_file).resolve() if schema_file else _default_schema_path(project_root)

        # ── Validate manifests ────────────────────────────────────
        console.print(f'\n[bold]Validating {len(plugin_dirs)} plugin(s)…[/bold]\n')

        valid_plugins: list[tuple[object, Path]] = []   # (manifest, plugin_path)
        has_error = False

        for pdir in plugin_dirs:
            manifest, err = _validate_one(pdir, validator)
            if err:
                console.print(f'[red]✗[/red] [cyan]{pdir.name}[/cyan] — {escape(err)}')
                has_error = True
            else:
                console.print(
                    f'[green]✓[/green] [cyan]{manifest.name}[/cyan] '  # type: ignore[union-attr]
                    f'v{manifest.version} [{manifest.execution_mode.value}]'  # type: ignore[union-attr]
                )
                valid_plugins.append((manifest, pdir))

        if has_error and not valid_plugins:
            raise typer.Exit(1)

        if not save and not check_breaking:
            if has_error:
                raise typer.Exit(1)
            return

        # ── Extract schemas from source (AST) — grouped by plugin ──
        console.print()
        # { plugin_name: {"actions": [...], "events": [...]} }
        per_plugin: dict[str, dict] = {}

        for manifest, pdir in valid_plugins:
            entry_attr = getattr(manifest, 'entry_point', 'src/main.py')
            src = _find_entry_point(pdir, entry_attr)
            if src is None:
                console.print(f'[yellow]  {manifest.name}: entry point not found — skipping[/yellow]')
                per_plugin[manifest.name] = {'actions': [], 'events': []}
                continue
            try:
                ipc, evts = _extract_from_source(manifest.name, src)
                per_plugin[manifest.name] = {'actions': ipc, 'events': evts}
                console.print(
                    f'  [dim]{manifest.name}:[/dim] '
                    f'[cyan]{len(ipc)}[/cyan] action(s), '
                    f'[cyan]{len(evts)}[/cyan] event subscription(s)'
                )
            except ValueError as exc:
                console.print(f'[yellow]  {manifest.name}: {escape(str(exc))}[/yellow]')
                per_plugin[manifest.name] = {'actions': [], 'events': []}

        # ── --save ────────────────────────────────────────────────
        if save:
            from xcore.kernel.schema import ActionSchema

            # Build JSON: { plugin_name: { "actions": {name: schema_dict}, "events": [...] } }
            snapshot: dict = {}
            for pname, data in per_plugin.items():
                actions_dict = {}
                for s in data['actions']:
                    # key = action name (short), value = full schema dict
                    actions_dict[s['action']] = ActionSchema(**s).to_dict()
                snapshot[pname] = {
                    'actions': actions_dict,
                    'events': data['events'],
                }

            snap_path.parent.mkdir(parents=True, exist_ok=True)
            snap_path.write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
            console.print(f'\n[green]✓[/green] Snapshot saved → [dim]{snap_path}[/dim]')

            # Summary tables
            all_ipc   = [s for d in per_plugin.values() for s in d['actions']]
            all_events = [e for d in per_plugin.values() for e in d['events']]

            if all_ipc:
                from rich.table import Table
                t = Table(title=f'IPC Actions ({len(all_ipc)})')
                t.add_column('Plugin', style='dim')
                t.add_column('Action', style='cyan')
                t.add_column('Version', style='magenta')
                t.add_column('Input', style='dim')
                t.add_column('Output', style='dim')
                for s in sorted(all_ipc, key=lambda x: (x['plugin'], x['action'])):
                    t.add_row(
                        s['plugin'], s['action'], s['version'],
                        ', '.join(s['input']) or '—',
                        ', '.join(s['output']) or '—',
                    )
                console.print(t)
            else:
                console.print('[dim]  No @action-decorated methods found.[/dim]')

            if all_events:
                from rich.table import Table
                t = Table(title=f'Event Subscriptions ({len(all_events)})')
                t.add_column('Plugin', style='dim')
                t.add_column('Event', style='cyan')
                t.add_column('Method', style='dim')
                t.add_column('Priority', style='magenta')
                for e in sorted(all_events, key=lambda x: (x.get('plugin', ''), x['event'])):
                    t.add_row(e.get('plugin', '?'), e['event'], e['method'], str(e['priority']))
                console.print(t)

        # ── --check-breaking ──────────────────────────────────────
        if check_breaking:
            from xcore.kernel.schema import ActionSchema, BreakingChangeDetector, SchemaRegistry

            if not snap_path.exists():
                console.print(
                    f'[yellow]⚠ No snapshot at [dim]{snap_path}[/dim].\n'
                    f'  Run with [cyan]--save[/cyan] first.[/yellow]'
                )
                raise typer.Exit(1)

            raw: dict = json.loads(snap_path.read_text(encoding='utf-8'))

            # Build previous registry from the per-plugin format
            previous = SchemaRegistry()
            prev_events_all: list[dict] = []
            for pname, pdata in raw.items():
                prev_actions = pdata.get('actions', {}) if isinstance(pdata, dict) else {}
                prev_events_all.extend(pdata.get('events', []) if isinstance(pdata, dict) else [])
                for aname, adict in prev_actions.items():
                    try:
                        previous._schemas[f'{pname}:{aname}'] = ActionSchema.from_dict(adict)  # noqa: SLF001
                    except Exception:
                        pass

            # Build current registry
            current = SchemaRegistry()
            curr_events_all: list[dict] = []
            for pname, data in per_plugin.items():
                curr_events_all.extend(data['events'])
                for s in data['actions']:
                    current.register(ActionSchema(**s))

            detector = BreakingChangeDetector(previous, current)
            breaking = detector.detect()

            console.print()
            if breaking:
                console.print(f'[red bold]✗ {len(breaking)} breaking change(s) detected:[/red bold]')
                for change in breaking:
                    console.print(f'[red]  {escape(str(change))}[/red]')
            else:
                console.print('[green]✓[/green] No breaking IPC changes detected.')

            # Event subscription diff (informational, not an error)
            prev_evt_keys = {(e.get('plugin', ''), e['event']) for e in prev_events_all}
            curr_evt_keys = {(e.get('plugin', ''), e['event']) for e in curr_events_all}
            removed = prev_evt_keys - curr_evt_keys
            added   = curr_evt_keys - prev_evt_keys
            if removed:
                console.print('[yellow]  Event subscriptions removed:[/yellow]')
                for plugin, ev in sorted(removed):
                    console.print(f'[yellow]    - {escape(plugin)}:{escape(ev)}[/yellow]')
            if added:
                console.print('[dim]  Event subscriptions added:[/dim]')
                for plugin, ev in sorted(added):
                    console.print(f'[dim]    + {plugin}:{ev}[/dim]')

            if breaking:
                raise typer.Exit(1)

        if has_error:
            raise typer.Exit(1)
