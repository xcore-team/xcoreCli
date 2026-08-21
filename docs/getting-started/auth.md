# Authentication

To interact with the **xcore marketplace** and install plugins, you need
two separate credentials — they protect different things and neither
substitutes for the other:

| Credential | What it's for | Where to get it |
|------------|----------------|------------------|
| **API key** (`xdk_...`) | Authorizes the download itself (`X-API-Key` header on `GET /plugins/{slug}/install`) — tied to one project (`kind=plugin`, matching the target plugin's slug) | XCoreHub → Déploiements → Projets & clés |
| **Signing key** | An HMAC-SHA256 secret used to verify the `X-Signature` header on the downloaded ZIP — installation is refused if it doesn't match | XCoreHub → Déploiements → Clé de signature |

`browse`/`search`/`info` (read-only discovery) need **neither** — the
marketplace listing is public.

## Configuration Commands

`xcorecli` provides a `config` command group to manage your local settings.

### Store your credentials

```bash title="Configuration"
xcli config set api-key xdk_...
xcli config set signing-key <your-signing-secret>
```

Both are required before `xcli plugin install <name>` will succeed —
`install` checks for each explicitly and tells you exactly which one is
missing.

!!! warning "Security First"
    Never share your API key or signing key, or commit them to version
    control. They're stored in `~/.xcli/config.json` (mode `0600`), never in
    your project's `integration.yaml`.

### View current configuration

To check your current configuration (with sensitive data masked):

```bash
xcli config show
```

## Credential storage

Managed by `xcli/_credentials.py` — a flat `~/.xcli/config.json`, keyed
`api-key` / `signing-key`. Only these two keys are valid; anything else
passed to `xcli config set` is rejected.

!!! info "Marketplace URL"
    By default, `xcorecli` connects to `https://marketplace.xcorehub.dev`.
    Override it via `marketplace.url` in the project's `integration.yaml`
    (the same value the project's own backend uses) — always include the
    `https://` scheme, a bare domain will fail to resolve as a URL.

## Environment variables

For CI/CD environments, both credentials can be supplied via environment
variables instead of `xcli config set` — these take priority over
`~/.xcli/config.json` when present:

```bash title=".env"
XCLI_API_KEY=xdk_...
XCLI_SIGNING_KEY=your-signing-secret
```
