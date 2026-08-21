from typer import Typer

from . import install_commands, marketplace_commands

_CTX = {'help_option_names': ['-h', '--help']}

app = Typer(
    help='Marketplace service-extension lifecycle (browse/install published '
    'xservices extensions). Not to be confused with `xcli services` / `xcli '
    'manager services`, which show the LOCAL xcore runtime status — a '
    'different, unrelated thing with a similar name.',
    context_settings=_CTX,
)

marketplace_app = Typer(help='Browse and search marketplace service extensions.', context_settings=_CTX)
app.add_typer(marketplace_app, name='marketplace')

install_commands.register(app)                # xcli service install / versions / remove / info / health
marketplace_commands.register(marketplace_app)  # xcli service marketplace browse / search / info
