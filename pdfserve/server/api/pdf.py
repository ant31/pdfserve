#!/usr/bin/env python3
# pylint: disable=no-name-in-module
# pylint: disable=too-few-public-methods
import asyncio
import logging
import tempfile
import uuid
from io import BytesIO
from pathlib import Path
from typing import Annotated, cast, BinaryIO

from fastapi import APIRouter, BackgroundTasks, File, Query, UploadFile
from fastapi.responses import FileResponse

from pdfserve.pdf import PdfFileInfo, PdfTransform #, StampImage, StampPdf, StampText, Color, Point, PositionEnum


router = APIRouter()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pdf", tags=["pdfserve"])

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
async def merge(
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
    outline: Annotated[bool, Query(description="create an outline with the name of the file as items")] = True,
) -> FileResponse:
    """
    Merge pdf files into one.

    - **name**: the name of the merged file, if not provided, a random name will be generated
    - **files**: a list of files to merge, can be a list of URL to download the file from or the uploaded file as binary object
    - **outline**: if True, create an outline with the name of the file, if False, no outline will be added
    """

    # if not name:
    #     uid = uuid.uuid4()
    #     name = f"merged_{uid}.pdf"
    # paths: list[BinaryIO | BytesIO | str | Path] = []
    # names = []
    # dlfiles = []
    # # 1 Download all files
    # for f in files:
    #     if isinstance(f, str):
    #         tmp = tempfile.SpooledTemporaryFile()
    #         a = DownloadClient().download(f, dest_dir=tmpdir.name, output=cast(BinaryIO, tmp))
    #         dlfiles.append(a)
    # # 1.1 Wait all to finish download
    # dlpaths: list[FileDownload] = list(await asyncio.gather(*dlfiles))
    # # 2 Order merge and names
    # i = 0
    # for f in files:
    #     if isinstance(f, str):
    #         if dlpaths[i].content is not None:
    #             paths.append(cast(BytesIO, dlpaths[i].content))
    #         names.append(dlpaths[i].filename)
    #         i += 1
    #     else:
    #         paths.append(f.file)
    #         names.append(f.filename)
    # if not outline:
    #     names = []
    # dest = Path(tmpdir.name, name)
    i = 0
    inputs= []
    for f in files:
        if not isinstance(f, str):
            content: BinaryIO = cast(BinaryIO, f.file)
            inputs.append(PdfFileInfo(content=content, filename=f.filename))
        else:
            inputs.append(f)
        i += 1
    logger.info("Merging: %s, outline: %s", str(inputs), outline)
    tmpf = tempfile.NamedTemporaryFile(delete=False)
    # background_tasks.add_task(tmpf.cleanup)

    output = await PdfTransform(files=inputs, dest_dir="", use_temporary=True).merge(name=name, output=tmpf, outline=outline)

    return FileResponse(tmpf.name, media_type="application/pdf", filename=str(output.filename))


# @router.post(
#     "/stamp", response_class=FileResponse, response_description="the input PDF with a stamp/watermark added", summary=""
# )
# async def stamp(
#     background_tasks: BackgroundTasks, files: list[UploadFile | str] = [], name: str | None = None, outline: bool = True
# ) -> FileResponse:
#     """
#     Merge pdf files into one.
#     #
#     - **name**: the name of the merged file, if not provided, a random name will be generated
#     - **files**: a list of files to merge, can be a list of URL to download the file from or the uploaded file as binary object
#     - **outline**: if True, create an outline with the name of the file, if False, no outline will be added
#     """

#     if not name:
#         uid = uuid.uuid4()
#         name = f"merged_{uid}.pdf"
#     paths: list[BinaryIO | str] = []
#     tmpdir = tempfile.TemporaryDirectory(delete=False)
#     background_tasks.add_task(tmpdir.cleanup)
#     names = []
#     dlfiles = []
#     # 1 Download all files
#     for f in files:
#         if isinstance(f, str):
#             a = DownloadClient().download(f, dest_dir=tmpdir.name)
#             dlfiles.append(a)
#     # 1.1 Wait all to finish download
#     dlpaths = list(await asyncio.gather(*dlfiles))
#     # 2 Order merge and names
#     i = 0
#     for f in files:
#         if isinstance(f, str):
#             paths.append(dlpaths[i])
#             names.append(Path(dlpaths[i]).name)
#             i += 1
#         else:
#             paths.append(f.file)
#             names.append(f.filename)
#     if not outline:
#         names = []
#     dest = Path(tmpdir.name, name)
#     logger.info("Merging: %s, outline: %s", str(paths), names)
#     pdf.merge(paths, output=dest, names=names)
#     return FileResponse(dest, media_type="application/pdf", filename=name)
