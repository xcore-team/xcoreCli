# Plugin Security & Signing

Security is a core pillar of the `xcore` plugin system. We provide tools to ensure that only verified and safe code runs in your environment.

## Signing Plugins

For production use, plugins should be signed to prevent tampering. Signing uses an HMAC-SHA256 hash based on the plugin's content and a secret key.

```bash title="Sign Plugin"
xcli plugin security sign my-plugin --key "your-secret-signing-key"
```

This creates a `plugin.sig` file within the plugin directory.

!!! note "Secret Key Management"
    The `plugins.secret_key` in your `integration.yaml` must match the key used for signing for verification to succeed.

## Verification & Health

You can manually verify the integrity of a plugin:

```bash
xcli plugin security verify my-plugin
```

For a comprehensive check of all plugins (including manifest validation and AST analysis), use:

```bash
xcli plugin health
```

## Strict Mode

Enable `strict_trusted` in your configuration to refuse any plugin that is not properly signed.

```yaml
plugins:
  strict_trusted: true
```

## AST Whitelisting

For **Sandboxed Plugins**, `xcore` uses an Abstract Syntax Tree (AST) analyzer to restrict imports.

- **Allowed**: `json`, `math`, `fastapi`, etc.
- **Forbidden**: `os`, `subprocess`, `shutil`, etc.

This prevents plugins from performing unauthorized filesystem or system operations.

!!! tip "Customizing Whitelists"
    Modify the `security.allowed_imports` section in `integration.yaml` to suit your project's needs.
