#!/usr/bin/env python3
# pylint: disable=no-value-for-parameter
# pylint: disable=too-many-arguments

import json
from pathlib import Path

import click

from pdfserve.pdf import PdfTransform, PositionEnum, StampImage, StampText
from pdfserve.putils import make_sync


async def stamp_all(
    ctx: click.Context, stamp: StampText | StampImage, files: list[str], dest: str, output: str
) -> None:
    pt = PdfTransform(files=files)
    outputs = None
    if dest:
        outputs = [Path(dest)]

    res = await pt.stamp(stamp=stamp, outputs=outputs)
    if output == "json":
        click.echo(json.dumps([x.model_dump() for x in res], indent=2, default=str))
    else:
        finfo = res[0]
        if finfo.path is not None:
            with open(finfo.path, "rb") as f:
                click.echo(f.read())
        else:
            if finfo.content is None:
                click.echo("No content")
            else:
                if isinstance(finfo.content, (Path, str)):
                    raise ValueError(f"Content is not a file-like object: {finfo.content}")
                finfo.content.seek(0)
                click.echo(finfo.content.read())
                finfo.content.close()
    ctx.exit()


@click.group()
@click.pass_context
def stampcli(ctx: click.Context) -> None:
    ctx.ensure_object(dict)


@stampcli.command(name="text")
@click.option("--output", "-o", default="json", type=click.Choice(["json", "text"]))
@click.option("--dest", "-d", default="", help="File to write the output to")
@click.option(
    "--position", "-p", default="TOP_RIGHT", type=click.Choice([x.name for x in PositionEnum]), help="Text position"
)
@click.option(
    "--files",
    "-f",
    default=[],
    multiple=True,
    help="Files to merge, can be a list of URL to download the file from, localfile",
)
@click.option("--text", "-t", required=True, help="Text to stamp")
@click.option("--font", default="Helvetica", help="Text font")
@click.option("--text-size", default=16, type=int, help="Text size")
@make_sync
@click.pass_context
async def stamp_text(
    ctx: click.Context, output: str, dest: str, files: list[str], text: str, font: str, text_size: int, position: str
) -> None:
    stamp = StampText(text=text, font=font, text_size=text_size, position_name=PositionEnum[position])
    await stamp_all(ctx, stamp, files, dest, output)


@stampcli.command(name="image")
@click.option("--output", "-o", default="json", type=click.Choice(["json", "text"]))
@click.option("--dest", "-d", default="", help="File to write the output to")
@click.option(
    "--position", "-p", default="TOP_RIGHT", type=click.Choice([x.name for x in PositionEnum]), help="Text position"
)
@click.option(
    "--files",
    "-f",
    default=[],
    multiple=True,
    help="Files to merge, can be a list of URL to download the file from, localfile",
)
@click.option("--image", "-i", required=True, help="Image to stamp")
@click.option("--scale", "-s", default=1.0, type=float, help="Image scale")
@click.option("--rotate", "-r", default=1, type=int, help="Image Rotation")
@make_sync
@click.pass_context
async def stamp_image(
    ctx: click.Context, output: str, dest: str, files: list[str], image: str, scale: float, rotate: int, position: str
) -> None:
    stamp = StampImage(image=image, scale=scale, angle=rotate, position_name=PositionEnum[position])
    await stamp_all(ctx, stamp, files, dest, output)
