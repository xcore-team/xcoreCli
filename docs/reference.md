# CLI Reference

A comprehensive list of all commands available in `xcorecli`.

## Global Commands

- `xcli init`: Initialize a new xcore project.
- `xcli upgrade`: Migrate `integration.yaml` to the latest schema.
- `xcli health`: Global health check of all configured services.
- `xcli services`: Show status and details of all system services.

## `manager`  Administration

- `manager start`: Start the FastAPI server (uvicorn).
- `manager stop`: Stop the detached API server.
- `manager top`: Full-screen live dashboard (resources + logs).
- `manager logs`: Stream and filter application logs.
- `manager resources`: Live resource usage per plugin.
- `manager metrics`: Application metrics snapshot.
- `manager services list`: List all services.
- `manager services reload`: Reconnect a service.
- `manager services unload`: Shutdown a service.

## `deploy`  Production Deployment

- `deploy init`: Generate a `xcore-deploy.yaml` template file.
- `deploy list`: Show targets, plugins, extensions, and hooks declared in the config.
- `deploy <target>`: Deploy integration.yaml + extensions + plugins to a remote server.
- `deploy status <target>`: Show plugin state on a remote server via the XCore API.

**Key options for `deploy <target>`:**

| Option | Description |
|---|---|
| `--plugin <name>` | Deploy only one plugin (skips extensions + integration) |
| `--dry-run` | Simulate without sending anything |
| `--no-reload` | Transfer files without triggering reload/restart |
| `--file <path>` | Use an alternate config file |

**Deploy order:** `integration.yaml` → extensions (services) → plugins

**Sources:** each plugin/extension accepts `source: ./local/path` OR `repo: https://github.com/org/repo` (public), with optional `token: "${GITHUB_TOKEN}"` for private repos or `git@github.com:...` SSH URLs.

**Hook levels:**

| Level | Keys | When |
|---|---|---|
| Global | `hooks.pre_deploy` / `hooks.post_deploy` | Once per full deploy run |
| Per-plugin/extension | `hooks.pre_deploy` / `post_deploy` | Before/after each item |

---

## `plugin`  Lifecycle

- `plugin info`: Detailed local plugin report.
- `plugin health`: Health check of all installed plugins.
- `plugin remove`: Uninstall a plugin.
- `plugin install`: Install from marketplace/git/zip.
- `plugin versions`: List marketplace versions.

### `plugin local`  Development
- `local scaffold`: Create a new plugin from template.
- `local link`: Symlink a local directory.
- `local unlink`: Remove a symlink.
- `local list`: List all plugins with link type.

### `plugin marketplace`  Discovery
- `marketplace browse`: List all available plugins.
- `marketplace search`: Search by keyword.
- `marketplace info`: Pre-install details.
- `marketplace trending`: Show popular plugins.
- `marketplace rate`: Rate 15 stars.

### `plugin update`  Maintenance
- `update check`: Check for new versions.
- `update apply`: Apply updates (--all, --dry-run).

### `plugin runtime`  Control
- `runtime load`: Activate a plugin.
- `runtime unload`: Deactivate a plugin.
- `runtime reload`: Restart a plugin.
- `runtime status`: Show active plugins.

## `worker`  Background Tasks

- `worker start`: Start a Celery worker.
- `worker beat`: Start the scheduler.
- `worker inspect`: List tasks and nodes.
- `worker purge`: Clear a task queue.

### `worker process`  Orchestration
- `process start`: Start multiple instances.
- `process stop`: Shutdown all workers.
- `process restart`: Restart all workers.
- `process status`: Table of running worker PIDs.
- `process logs`: Tail worker-specific logs.

## `migration`  Database

- `migration init`: Setup Alembic.
- `migration scan`: Preview discovered models.
- `migration backup`: Create a DB backup.
- `migration restore`: Restore from backup.
- `migration backups`: List available backups.
- `migration revision`: Create a new migration.
- `migration upgrade`: Apply migrations (--backup).
- `migration downgrade`: Rollback migrations.
- `migration history`: Show migration list.
