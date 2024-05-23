#!/usr/bin/env python3
# pylint: disable=no-name-in-module
# pylint: disable=too-few-public-methods
import logging
import os
import tempfile
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, Query, UploadFile
from fastapi.exceptions import HTTPException
from fastapi.responses import FileResponse
from pydantic import Json

from pdfserve.pdf import PdfFileInfo, PdfTransform, StampImage, StampText
from pdfserve.server.utils import form_body

router = APIRouter()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pdf", tags=["pdfserve"])


StampTextForm = form_body("")(StampText)
StampImageForm = form_body("")(StampImage)


def prepare_files(files: list[UploadFile | str]) -> list[PdfFileInfo]:
    inputs = []
    for f in files:
        if not isinstance(f, str):
            if f.filename is None:
                f.filename = ""
            inputs.append(PdfFileInfo(content=f.file, filename=f.filename))
        else:
            inputs.append(f)
    return inputs


def cleanup(tmpf):
    if hasattr(tmpf, "cleanup"):
        tmpf.cleanup()
    else:
        try:
            os.unlink(tmpf.name)
        except FileNotFoundError:
            pass


# pylint: disable=dangerous-default-value
@router.post(
    "/merge",
    response_class=FileResponse,
    response_description="The merged PDF file",
    summary="Merge pdf files into one.",
    responses={
        200: {
            "description": "The merged PDF file",
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def merge_pdf(
    background_tasks: BackgroundTasks,
    files: Annotated[
        list[UploadFile | str],
        File(
            default_factory=list,
            title="Files",
            description="a list of files to merge, can be a list of URL to download the file from or the uploaded file as binary object",
        ),
    ] = [],
    name: Annotated[
        str, Query(description="the name of the merged file, if not provided, a random name will be generated")
    ] = "",
    dpi: Annotated[int, Query(description="DPI to use for input images")] = 96,
    outline: Annotated[bool, Query(description="create an outline with the name of the file as items")] = True,
) -> FileResponse:
    """
    Merge pdf files into one.

    - **name**: the name of the merged file, if not provided, a random name will be generated
    - **files**: a list of files to merge, can be a list of URL to download the file from or the uploaded file as binary object
    - **outline**: if True, create an outline with the name of the file, if False, no outline will be added
    """
    inputs = prepare_files(files)
    logger.info("Merging: %s, outline: %s", str(inputs), outline)
    with tempfile.NamedTemporaryFile(suffix=".pdf", mode="w+b", delete=False) as tmpf:
        background_tasks.add_task(cleanup, tmpf)
        pt = PdfTransform(files=inputs, dest_dir="", use_temporary=True, dpi=dpi)
        output = await pt.merge(name=name, output=tmpf.file, outline=outline)
        if output is None:
            raise ValueError("No output")
        return FileResponse(tmpf.name, media_type="application/pdf", filename=output.filename)


async def stamp_all(
    background_tasks: BackgroundTasks,
    files: list[UploadFile | str],
    stamp: StampText | StampImage,
    name: str = "",
    merge: bool = True,
) -> FileResponse:
    inputs = prepare_files(files)
    logger.info("Stamping: %s, stamp: %s", str(inputs), str(stamp.model_dump_json(indent=2)))
    with tempfile.NamedTemporaryFile(suffix=".pdf", mode="w+b", delete=False) as tmpf:
        background_tasks.add_task(cleanup, tmpf)
        pt = PdfTransform(files=inputs, dest_dir="", use_temporary=True)
        if merge:
            merged = await pt.merge()
            pt.set_files([merged])
        outputs = await pt.stamp(name=name, stamp=stamp, outputs=[tmpf.file])
        if not outputs:
            raise ValueError("No output")
        return FileResponse(tmpf.name, media_type="application/pdf", filename=outputs[0].filename)


# pylint: disable=dangerous-default-value
@router.post(
    "/stamp",
    response_class=FileResponse,
    response_description="PDF file with the stamp applied",
    summary="Apply Stamp",
    responses={
        200: {
            "description": "PDF file with the stamp applied",
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def stamp_sync(
    background_tasks: BackgroundTasks,
    files: Annotated[
        list[UploadFile | str],
        File(
            title="Files",
            description="a list of files to merge, can be a list of URL to download the file from or the uploaded file as binary object",
        ),
    ],
    stamp_text: Annotated[Json[StampText] | None, Form(title="StampText JSON")] = None,
    stamp_image: Annotated[Json[StampImage] | None, Form(title="StampImage JSON")] = None,
    # stamp_text: Annotated[StampText | None, Depends(StampTextForm)] = None,
    # stamp_image: Annotated[StampImage | None, Depends(StampImageForm)] = None,
    merge: Annotated[bool, Query(description="Merge the files before stamping")] = True,
    stamp_file: Annotated[
        UploadFile | str,
        File(
            title="Stamp Image",
            description="The stamp as an image or pdf to use",
        ),
    ] = "",
    name: Annotated[
        str, Query(description="the name of the merged file, if not provided, a random name will be generated")
    ] = "",
) -> FileResponse:
    """
    Apply a stamp on top of a PDF

    - **name**: the name of the stamped file, if not provided, a random name will be generated
    - **files**: a list of files to stamp, can be a list of URL to download the file from or the uploaded file as binary object
    - **stamp**: the stamp to apply as a serialized JSON string of the StampText Model
    - **stamp_image**: the stamp as an image or pdf to use
    - **stamp_text**: the stamp as an image or pdf to use
    - **stamp_file**: the stamp as an image or pdf to use
    - **merge**: if True, merge the files before stamping, if False, stamp each file separately (always True, not implemented)
    """
    stamp = None

    if stamp_file:
        if not stamp_image:
            stamp_image = StampImage()
        if isinstance(stamp_file, str):
            stamp_image._image = await stamp_image.load_image(stamp_file)
        else:
            stamp_image._image = stamp_file.file
        stamp = stamp_image
    elif stamp_text:
        stamp = stamp_text
    else:
        raise HTTPException(status_code=422, detail="stamp_text or stamp_image missing")

    return await stamp_all(background_tasks, files, stamp, name=name, merge=merge)
