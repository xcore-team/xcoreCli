# Installing Plugins

Plugins can be installed from the official **xcore Marketplace** or from external sources like Git repositories.

## Installing from Marketplace

The easiest way to add features. `xcorecli` handles downloads and HMAC signature verification.

!!! warning "Two credentials required"
    Marketplace installs need **both** an API key and a signing key
    configured first — see [Authentication](../getting-started/auth.md).
    Missing either one fails fast with a clear message telling you which
    one and how to set it; nothing is extracted until the signature checks
    out.

```bash title="Marketplace Install"
xcli plugin install name-of-plugin
```

!!! tip "Shortcut"
    `xcli install name-of-plugin` works too — a top-level alias for
    `xcli plugin install`, same command underneath.

### Installing a Specific Version

```bash
xcli plugin install name-of-plugin@1.2.3
```

To see all available versions for a plugin:
```bash
xcli plugin versions name-of-plugin
```

## Installing from Git or URL

You can install plugins directly from a Git repository or a hosted `.zip` file.

```bash title="Git Install"
xcli plugin install my-plugin --source git --url https://github.com/user/plugin.git
```

## Management Commands

### Detailed Info

Get a full report on an installed plugin, including its author, description, requested permissions, and resource limits.

```bash
xcli plugin info name-of-plugin
```

### Health Check

Verify the integrity of all installed plugins. This checks if manifests are valid, signatures match, and if sandboxed plugins follow AST import rules.

```bash
xcli plugin health
```

### Removal

Uninstall a plugin and remove its directory.

```bash
xcli plugin remove name-of-plugin
```

!!! warning "Security"
    `xcorecli` verifies the HMAC signature of marketplace plugins. For Git or local installs, we recommend running `xcli plugin health` after installation.
