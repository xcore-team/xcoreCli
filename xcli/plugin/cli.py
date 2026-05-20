from typer import Typer

from .install_commands import register as register_install_commands
from .local_commands import register as register_local_commands
from .marketplace_commands import register as register_marketplace_commands
from .runtime_commands import register as register_runtime_commands
from .security_commands import register as register_security_commands
from .update_commands import register as register_update_commands

_CTX = {'help_option_names': ['-h', '--help']}
app = Typer(help='Plugin management.', context_settings=_CTX)

register_local_commands(app)
register_install_commands(app)
register_runtime_commands(app)
register_marketplace_commands(app)
register_security_commands(app)
register_update_commands(app)
