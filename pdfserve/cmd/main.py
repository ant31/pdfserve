#!/usr/bin/env python3
import click
from ant31box.cmd.default_config import default_config
from ant31box.cmd.version import version

from pdfserve.config import config
from pdfserve.version import VERSION

from .merge import merge
from .server import server
from .stamp import stampcli


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    ctx.ensure_object(dict)


def main():
    _ = VERSION
    _ = config()
    # start the FastAPI server
    cli.add_command(server)
    # Display version
    cli.add_command(version)
    # Show default config
    cli.add_command(default_config)
    # Merge PDF and images files
    cli.add_command(merge)
    # Stamp pdf
    cli.add_command(stampcli, name="stamp")

    # Parse cmd-line arguments and options
    # pylint: disable=no-value-for-parameter
    cli()


if __name__ == "__main__":
    main()
