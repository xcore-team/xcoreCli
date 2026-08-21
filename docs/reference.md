# CLI Reference

A comprehensive list of all commands available in `xcorecli`.

## Global Commands

- `xcli init`: Initialize a new xcore project.
- `xcli upgrade`: Migrate `integration.yaml` to the latest schema.
- `xcli login`: Authorize this machine with the marketplace (device-code flow).
- `xcli install`: Shortcut for `xcli plugin install`.
- `xcli health`: Global health check of all configured services.
- `xcli services`: Show status and details of all system services (local
  runtime — not the marketplace catalog, see `xcli service` below).

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

!!! info "Production deployment moved"
    `deploy` (init/list/status, SSH transfer, pre/post hooks) is no
    longer part of `xcorecli` — it's fully replaced by the standalone
    [`xcore-agent`](https://github.com/traoreera/xcore-agent) deployment
    agent.

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
- `marketplace browse`: List published plugins (`--sort newest|downloads|rating`).
- `marketplace search`: Search by name or description.
- `marketplace info`: Pre-install details, including published versions.

No `rate` command — rating requires a full user session (JWT), not an API
key; rate plugins from the XCoreHub dashboard.

### `plugin update`  Maintenance
- `update check`: Check for new versions.
- `update apply`: Apply updates (--all, --dry-run).

### `plugin runtime`  Control
- `runtime load`: Activate a plugin.
- `runtime unload`: Deactivate a plugin.
- `runtime reload`: Restart a plugin.
- `runtime status`: Show active plugins.

## `service`  Marketplace Extensions

Mirror of `plugin` for the separate `xservices` catalog — not to be
confused with `xcli services`/`xcli manager services` (local runtime).

- `service info`: Detailed local extension report.
- `service health`: Health check of all installed extensions.
- `service remove`: Uninstall an extension.
- `service install`: Install from marketplace.
- `service versions`: List marketplace versions.

### `service marketplace`  Discovery
- `marketplace browse`: List published extensions (`--sort newest|installs|rating`).
- `marketplace search`: Search by name or description.
- `marketplace info`: Pre-install details, including published versions.

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
