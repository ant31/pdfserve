#!/usr/bin/env python3
import asyncio
import logging
import tempfile
import uuid
from enum import StrEnum
from io import BytesIO, IOBase
from pathlib import Path
from typing import IO, Any, BinaryIO, Literal, Sequence, TypeAlias, cast

from fpdf import FPDF
from PIL import Image as PILImage
from PIL.Image import Image
from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader, PdfWriter

from pdfserve.client.filedl import DownloadClient

PDFInput: TypeAlias = str | BinaryIO | IO[Any] | PdfReader | Path  | tempfile.SpooledTemporaryFile | Any
PDFOutput: TypeAlias = IO[Any] | Path | str  | tempfile.SpooledTemporaryFile

logger: logging.Logger = logging.getLogger(__name__)



# pylint: disable=invalid-name
class Color(BaseModel):
    r: int = Field(default=0)
    g: int = Field(default=-1)
    b: int = Field(default=-1)


class Point(BaseModel):
    x: int = Field(default=0)
    y: int = Field(default=0)


# pylint: enable=invalid-name
class PositionEnum(StrEnum):
    TOP_LEFT = "tl"
    CENTER = "c"
    TOP_RIGHT = "tr"
    BOTTOM_LEFT = "bl"
    BOTTOM_RIGHT = "br"
    TOP = "t"
    BOTTOM = "b"
    LEFT = "l"
    RIGHT = "r"


def get_position(
    pdf: FPDF,
    position: Point | None,
    position_name: PositionEnum = PositionEnum.TOP_LEFT,
    offset: Point = Point(x=0, y=0),
) -> Point:
    if not position:
        if position_name == PositionEnum.TOP_LEFT:
            position = Point(x=10, y=10)
        elif position_name == PositionEnum.TOP_RIGHT:
            position = Point(x=-15, y=10)
        elif position_name == PositionEnum.BOTTOM_LEFT:
            position = Point(x=10, y=-10)
        elif position_name == PositionEnum.BOTTOM_RIGHT:
            position = Point(x=-15, y=-10)
        elif position_name == PositionEnum.TOP:
            position = Point(x=int(pdf.epw / 2), y=10)
        elif position_name == PositionEnum.BOTTOM:
            position = Point(x=int(pdf.epw / 2), y=-10)
        elif position_name == PositionEnum.LEFT:
            position = Point(x=10, y=int(pdf.eph / 2))
        elif position_name == PositionEnum.RIGHT:
            position = Point(x=-15, y=int(pdf.eph / 2))
        elif position_name == PositionEnum.CENTER:
            position = Point(x=int(pdf.epw / 2), y=int(pdf.eph / 2))
        else:
            raise ValueError(f"Invalid position name: {position_name}")
    return Point(x=position.x + offset.x, y=position.y + offset.y)


class BaseStamp(BaseModel):
    over: bool = Field(default=False)


class BaseCustomStamp(BaseStamp):
    page_format: tuple[float, float] | Literal["a3", "a4", "a5", "letter", "legal"] = Field(default="a4")
    opacity: float = Field(default=1.0)
    border: bool = Field(default=False)
    border_width: int = Field(default=1)
    background: bool = Field(default=False)
    background_color: Color = Field(default=Color(r=255, g=255, b=255))
    position: Point | None = Field(default=None)
    position_name: PositionEnum = Field(default=PositionEnum.TOP_LEFT)
    position_offset: Point = Field(default=Point(x=0, y=0))

    def get_position(self, pdf: FPDF) -> Point:
        return get_position(pdf, self.position, self.position_name, self.position_offset)

    def render_pdf(self, pdf: FPDF) -> FPDF:
        return pdf

    def to_pdf(self) -> PdfReader:
        pdf = FPDF()
        pdf.add_page(format=self.page_format)
        position = self.get_position(pdf)
        pdf.set_fill_color(r=self.background_color.r, g=self.background_color.g, b=self.background_color.b)
        pdf.set_xy(position.x, position.y)
        with pdf.local_context(fill_opacity=self.opacity, stroke_opacity=self.opacity):
            self.render_pdf(pdf)
        return PdfReader(BytesIO(pdf.output()))


class StampImage(BaseCustomStamp):
    image: Path | str = Field(...)
    angle: int = Field(default=0)
    scale: float = Field(default=1)

    def render_pdf(self, pdf: FPDF) -> FPDF:
        img = PILImage.open(self.image).convert("RGBA")
        if self.angle:
            img = img.rotate(self.angle)
        pdf.image(img, w=img.width * self.scale, h=img.height * self.scale)
        return pdf


class StampText(BaseCustomStamp):
    text: str = Field(default="")
    font: str = Field(default="Helvetica")
    size: int = Field(default=16)
    color: Color = Field(default=Color(r=255, g=0, b=0))

    def render_pdf(self, pdf: FPDF) -> FPDF:
        pdf.set_font(self.font, size=self.size)
        pdf.set_text_color(r=self.color.r, g=self.color.g, b=self.color.b)
        pdf.cell(text=self.text, border=self.border, fill=self.background)
        return pdf


class StampPdf(BaseStamp):
    """
    Stamp a PDF file with another PDF file.
    No modification is done to the original file and stamp file, they are just merged together.
    """

    input_stamp: Path | str = Field(...)

    def to_pdf(self) -> PdfReader:
        return PdfReader(self.input_stamp)


class PdfFileInfo(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    filename: Path = Field(default=Path(""))
    content: PDFInput | None  = Field(default=None)
    path: Path = Field(default=None)
    source: Path | str | None = Field(default=None)
    image: Image | None = Field(default=None)
    scale: float = Field(default=1)
    rotate: int = Field(default=0)
    pdf: PDFInput | None = Field(default=None)


class PdfTransform:
    def __init__(
        self, files: Sequence[BinaryIO | PdfFileInfo | str | Path | Image], dest_dir: str = "", use_temporary: bool = True
    ):
        self._input_files = files
        self.dest_dir = dest_dir
        self.use_temporary = use_temporary
        self._loaded = False
        self._files = []

    def reload(self):
        self.files = []

    @property
    async def files(self) -> list[PdfFileInfo]:
        if not self._loaded:
            self._files = await self.load_files(
                files=self._input_files, dest_dir=self.dest_dir, use_temporary=self.use_temporary
            )
            self._loaded = True
        return self._files

    @files.setter
    def files(self, files: list[BinaryIO | PdfFileInfo | str | Path | Image]):
        self._input_files = files
        self._loaded = False

    async def load(
        self, fileinput: PdfFileInfo | str | Path | Image, dest_dir: str = "", use_temporary: bool = True
    ) -> PdfFileInfo:
        if isinstance(fileinput, (str, Path)):
            info = await self.download_file(fileinput, dest_dir=dest_dir, use_temporary=use_temporary)
        elif isinstance(fileinput, Image):
            info = PdfFileInfo(filename=Path(fileinput.filename), source=fileinput.filename, image=fileinput)
        elif isinstance(fileinput, BinaryIO):
            info = PdfFileInfo(filename=Path(""), content=fileinput)
        elif isinstance(fileinput, PdfFileInfo):
            info = await self.load_image(fileinput)
        else:
            raise ValueError(f"Invalid file type: {type(fileinput)}")

        if not info.pdf:
            if info.content:
                info.pdf = info.content
            elif info.path:
                info.pdf = info.path
            else:
                raise ValueError(f"Invalid file: {info}, missing content or path or pdf")
        return info

    async def download_file(self, source: str | Path, dest_dir: str = "", use_temporary: bool = True) -> PdfFileInfo:
        tmp = Path("")
        if use_temporary:
            tmp = tempfile.SpooledTemporaryFile(dir=dest_dir)
        finfo = await DownloadClient().download(source, dest_dir=dest_dir, output=cast(BinaryIO, tmp))
        p = PdfFileInfo(
            filename=Path(finfo.filename),
            source=finfo.source,
            path=Path(str(finfo.path)),
            content=finfo.content,
            image=None,
        )
        return await self.load_image(p)

    async def load_image(self, pdfinfo: PdfFileInfo) -> PdfFileInfo:
        # skip pdf or if image is already loaded
        if pdfinfo.filename.suffix == ".pdf" or pdfinfo.pdf:
            return pdfinfo
        try:
            if pdfinfo.content:
                pdfinfo.image = PILImage.open(pdfinfo.content)
            else:
                pdfinfo.image = PILImage.open(pdfinfo.path)
        except PILImage.UnidentifiedImageError as e:
            # Skip non-image files
            logger.debug("Failed to open image: %s", e)
        pdfinfo.pdf = await self._img_to_pdf(pdfinfo.image, pdfinfo.path, scale=pdfinfo.scale)
        return pdfinfo

    async def load_files(
        self, files: list[BinaryIO | PdfFileInfo | str | Path | Image], dest_dir: str = "", use_temporary: bool = True
    ) -> Sequence[PdfFileInfo]:
        return await asyncio.gather(*[self.load(f, dest_dir=dest_dir, use_temporary=use_temporary) for f in files])

    async def merge(
        self,
        name: str = "",
        output: PDFOutput | None = None,
        outline_items: list[str] | None = None,
        outline: bool = True,
    ) -> PdfFileInfo:
        """
        Merge pdf files into one.
        Any files that don't have .pdf extension will be considered as images and converted to pdf.

        - **files**: a list of files to merge, can be a list of URL to download the file from or the uploaded file as binary object, or images
        - **name**: the name of the merged file, if not provided, a random name will be generated
        - **outline**: if True, create an outline with the name of the file, if False, no outline will be added
        """
        if not name:
            name = f"merged_{uuid.uuid4()}.pdf"
        contents = [f.pdf for f in await self.files]

        names = outline_items
        if outline and not names:
            names = [f.filename for f in await self.files]
        if not output:
            output = tempfile.SpooledTemporaryFile(dir=self.dest_dir)
        logger.info("Merging: %s, outline: %s", str(contents), names)
        result = self._merge(contents, output=output, names=names)
        return PdfFileInfo(filename=name, content=cast(BinaryIO, result), pdf=result)

    def split(self) -> list[PDFOutput]:
        raise NotImplementedError("Not implemented yet")

    def _img_to_pdf(self, image: Image | Path | str, output: PDFOutput, scale: float) -> PDFOutput:
        pdf = FPDF()
        pdf.add_page()
        if isinstance(image, (Path, str)):
            image = PILImage.open(image)
        pdf.image(image, w=image.width * scale, h=image.height * scale)
        imgpdf = PdfReader(BytesIO(pdf.output()))
        writer = PdfWriter()
        writer.append(imgpdf)
        success, _ = writer.write(output)
        if not success:
            raise ValueError("Failed to write the output file")

        return output

    def _merge(self, files: Sequence[PDFInput], output: PDFOutput, names: list[str] | None = None) -> PDFOutput:
        merger = PdfWriter()
        if not files:
            raise ValueError("No files to merge")
        if names and (len(names) == len(files)):
            for f, n in zip(files, names):
                merger.append(f, outline_item=n)
        else:
            for f in files:
                merger.append(f)
        merger.write(output)
        merger.close()
        return output

    # def stamp(
    #     self,
    #     fileinput: PDFInput,
    #     output: PDFOutput,
    #     stamp: StampPdf | StampText | StampImage,
    #     pages: set[int] | None = None,
    # ) -> PDFOutput:
    #     """
    #     Stamp a PDF file with a text string.

    #     :param file: the input PDF file
    #     :param output: the output PDF file
    #     :param stamp: the stamp to apply
    #     :param pages: the pages to stamp, if None, all pages will be stamped
    #     """
    #     writer = PdfWriter(clone_from=fileinput)
    #     p = 0
    #     stamp_pdf = stamp.to_pdf().pages[0]
    #     for page in writer.pages:
    #         if pages and p not in pages:
    #             continue
    #         page.merge_page(stamp_pdf, over=stamp.over)
    #     success, _ = writer.write(output)
    #     if not success:
    #         raise ValueError("Failed to write the output file")
    #     return output
