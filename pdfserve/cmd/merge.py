#!/usr/bin/env python3
import asyncio
import functools
import click

from pdfserve.pdf import PdfTransform

def make_sync(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return asyncio.run(func(*args, **kwargs))
    return wrapper

@click.command()
@click.option("--output", "-o", default="", help="File to write the output to")
@click.option("--files", "-f", default=[], multiple=True, help="Files to merge, can be a list of URL to download the file from, localfile")
@click.pass_context
@make_sync
async def merge(ctx: click.Context, output: str, files: list[str]) -> None:
    print("files", files)
    pt = PdfTransform(files=files)
    await pt.merge(output=output)
    ctx.exit()
