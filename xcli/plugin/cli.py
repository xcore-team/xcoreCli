from typer import Typer

from .install_commands import register as register_install_commands
from .local_commands import register as register_local_commands
from .marketplace_commands import register as register_marketplace_commands
from .runtime_commands import register as register_runtime_commands
from .security_commands import register as register_security_commands
from .update_commands import register as register_update_commands

_CTX = {'help_option_names': ['-h', '--help']}

app = Typer(help='Plugin lifecycle management.', context_settings=_CTX)

# ── Sub-groups ────────────────────────────────────────────────
local_app       = Typer(help='Local plugin development (scaffold, link, list).', context_settings=_CTX)
runtime_app     = Typer(help='Runtime control (load, unload, reload, status).', context_settings=_CTX)
marketplace_app = Typer(help='Browse and search marketplace plugins.', context_settings=_CTX)
security_app    = Typer(help='Sign and verify plugin integrity.', context_settings=_CTX)
update_app      = Typer(help='Check and apply plugin updates.', context_settings=_CTX)

app.add_typer(local_app,       name='local')
app.add_typer(runtime_app,     name='runtime')
app.add_typer(marketplace_app, name='marketplace')
app.add_typer(security_app,    name='security')
app.add_typer(update_app,      name='update')

# ── Command registration ───────────────────────────────────────
register_install_commands(app)      # xcli plugin install / versions / remove / info / health
register_local_commands(local_app)          # xcli plugin local scaffold / link / unlink / list
register_runtime_commands(runtime_app)      # xcli plugin runtime load / unload / reload / reload-all / status / call
register_marketplace_commands(marketplace_app)  # xcli plugin marketplace browse / search / info
register_security_commands(security_app)    # xcli plugin security sign / verify / validate
register_update_commands(update_app)        # xcli plugin update check / <name> --all --dry-run
