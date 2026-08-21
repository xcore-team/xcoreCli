# xcli — xcore project manager

Official CLI for the `xcore` framework: scaffold a project, manage
plugins (local dev, marketplace install, runtime control, signing), run
migrations, control the Celery worker, and monitor a running deployment.

```bash
pip install xcorecli
xcli --help
```

Full docs: https://docs.xcorehub.dev (built from `docs/` with
`mkdocs-material` — `mkdocs serve` locally).

## Quick start

```bash
xcli init my-app                # scaffold a new xcore project
cd my-app
pip install -r requirements.txt
xcli manager start --reload     # run it
```

## Installing plugins from the marketplace

Browsing is public, no credentials needed:

```bash
xcli plugin marketplace browse
xcli plugin marketplace search "auth"
xcli plugin marketplace info xlicense
```

Installing needs two credentials — see
[docs/getting-started/auth.md](docs/getting-started/auth.md):

```bash
xcli config set api-key xdk_...
xcli config set signing-key <your-signing-secret>
xcli plugin install xlicense
```

## Command groups

| Group | Purpose |
|-------|---------|
| `xcli init` / `xcli upgrade` | Scaffold a project / migrate `integration.yaml` to the latest schema |
| `xcli health` / `xcli services` | Health-check and status of all configured services |
| `xcli config` | Store local credentials (`api-key`, `signing-key`) |
| `xcli plugin` | Local dev, marketplace browse/install, runtime control, signing, updates — see `xcli plugin --help` |
| `xcli deploy` | Deploy plugins to remote servers |
| `xcli sandbox` | Inspect the plugin sandbox |
| `xcli worker` | Manage Celery workers |
| `xcli manager` | Runtime monitoring of a running instance |
| `xcli migration` | Alembic migrations for plugins |

Short hidden aliases exist for the busiest groups: `p` (plugin), `sb`
(sandbox), `w` (worker), `m` (manager), `mig` (migration).

`xcli` expects to run **inside** an xcore project directory (it reads that
project's `integration.yaml` and needs `xcore` importable in the current
environment) — it's a project-management tool, not a standalone service.
