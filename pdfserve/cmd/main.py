#!/usr/bin/env python3
import click

from .default_config import default_config
from .server import server
from .version import version
from .merge import merge

@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    ctx.ensure_object(dict)


def main():
    # start the FastAPI server
    cli.add_command(server)
    # Display version
    cli.add_command(version)
    # Show default config
    cli.add_command(default_config)
    # Merge PDF files
    cli.add_command(merge)

    # Parse cmd-line arguments and options
    # pylint: disable=no-value-for-parameter
    cli()


if __name__ == "__main__":
    main()
