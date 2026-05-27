# Plugin Sandboxing

The Sandbox provides a secure execution environment for third-party or untrusted plugins, ensuring they cannot compromise the host system.

## Resource Isolation

Sandboxed plugins are restricted in their resource consumption to prevent "noisy neighbor" issues or intentional Denial of Service.

### Limits Configuration

You can define default limits in `integration.yaml`:

```yaml
security:
  rate_limit_default:
    calls: 200        # Max IPC calls
    period_seconds: 60 # Per minute
```

## AST-Based Whitelisting

The core of the sandbox is an AST (Abstract Syntax Tree) analyzer that scans the plugin's code before execution.

- **Whitelisted**: Only modules listed in `security.allowed_imports` can be imported.
- **Blacklisted**: Modules in `security.forbidden_imports` (like `os` or `subprocess`) are explicitly blocked.

!!! danger "Sandbox Bypass"
    Attempting to bypass the sandbox via reflection or other advanced Python techniques is monitored and will result in the plugin being immediately unloaded.

## Managing the Sandbox

Use the `sandbox` command group to inspect the status of the isolation layer.

```bash
# View sandbox statistics
xcli sandbox stats

# Inspect a specific plugin's sandbox
xcli sandbox inspect my-sandboxed-plugin
```

!!! info "Trusted vs. Sandboxed"
    By default, plugins are treated as **Sandboxed**. You must explicitly mark a plugin as **Trusted** in its `plugin.yaml` (and usually sign it) to run it with full permissions.
