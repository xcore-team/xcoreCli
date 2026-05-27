# CLI Configuration

The `config` command group allows you to manage the behavior of `xcorecli` itself and its interaction with the `xcore` project.

## Commands Overview

| Command | Description |
|---------|-------------|
| `show`  | Display the current merged configuration. |
| `get`   | Retrieve a specific configuration value. |
| `set`   | Update a configuration value. |
| `validate` | Check `integration.yaml` for schema compliance. |

## Managing Settings

### Viewing Configuration

To see your current setup, including defaults and overrides from `integration.yaml`:

```bash
xcli config show
```

### Updating Values

You can modify settings directly from the CLI. These changes are typically applied to your local configuration or the project's `integration.yaml`.

```bash title="Set Value"
xcli config set app.debug true
```

!!! note "Layered Configuration"
    `xcorecli` uses a layered approach:
    1. Internal Defaults
    2. `integration.yaml` (Project level)
    3. Local CLI Config (User level)
    4. Environment Variables

## Runtime Configuration

Some settings in the `runtime` section of `integration.yaml` can be adjusted without restarting the entire system, such as plugin reload intervals.

```yaml
plugins:
  interval: 5 # Check for changes every 5 seconds
```

!!! info "Dynamic Updates"
    Use `xcli manager services reload` to apply certain configuration changes on the fly.
