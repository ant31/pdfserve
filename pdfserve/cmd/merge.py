#!/usr/bin/env python3
from pathlib import Path

import click

from pdfserve.pdf import PdfTransform
from pdfserve.putils import make_sync


@click.command()
@click.option("--output", "-o", default="json", type=click.Choice(["json", "text"]))
@click.option("--dest", "-d", default="", help="File to write the output to")
@click.option(
    "--files",
    "-f",
    default=[],
    multiple=True,
    help="Files to merge, can be a list of URL to download the file from, localfile",
)
@make_sync
@click.pass_context
async def merge(ctx: click.Context, output: str, dest: str, files: list[str]) -> None:
    pt = PdfTransform(files=files)
    res = await pt.merge(output=Path(dest))
    if output == "json":
        click.echo(res.model_dump_json(indent=2))
    else:
        if res.path is not None:
            with open(res.path, "rb") as f:
                click.echo(f.read())
        else:
            if res.content is None:
                click.echo("No content")
            else:
                if isinstance(res.content, (Path, str)):
                    raise ValueError(f"Content is not a file-like object: {res.content}")
                res.content.seek(0)
                click.echo(res.content.read())
    ctx.exit()
