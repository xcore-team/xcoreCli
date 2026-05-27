# Authentication

To interact with the **xcore marketplace** and perform secure operations, you need to configure your credentials.

## Configuration Commands

`xcorecli` provides a `config` command group to manage your local settings.

### Set Authentication Token

Use the `set` command to store your marketplace API key:

```bash title="Configuration"
xcli config set marketplace.api_key "your-secure-token"
```

!!! warning "Security First"
    Never share your API keys or commit them to version control. `xcorecli` stores these credentials securely in your local environment.

### View Current Configuration

To check your current configuration (with sensitive data masked):

```bash
xcli config show
```

## Credential Storage

Credentials and sensitive settings are managed by the `xcli/_credentials.py` module, which ensures that:
- API keys are handled securely.
- Tokens are used for marketplace interactions (`marketplace.xcorehub.dev`).

!!! info "Marketplace Integration"
    By default, `xcorecli` connects to `https://marketplace.xcorehub.dev`. You can override this URL in your `integration.yaml` or via the `config` command.

## Environment Variables

Alternatively, you can use environment variables for CI/CD environments:

```bash title=".env"
XCORE_MARKETPLACE_API_KEY=your-token
```
