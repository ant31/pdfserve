#!/usr/bin/env python3
from email.utils import parseaddr
from io import BytesIO
from enum import StrEnum
from typing import IO, Any, BinaryIO, Sequence, TypeAlias, Literal
from pypdf import PdfWriter, PdfReader
from pathlib import Path
from pydantic import BaseModel, Field
from PIL import Image as PILImage
from PIL.Image import Image
from fpdf import FPDF

PDFInput: TypeAlias = str | BinaryIO | IO[Any] | PdfReader | Path
PDFOutput: TypeAlias = IO[Any] | Path | str

class Color(BaseModel):
    r: int = Field(default=0)
    g: int = Field(default=-1)
    b: int = Field(default=-1)

class Point(BaseModel):
    x: int = Field(default=0)
    y: int = Field(default=0)

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

def get_position(pdf: FPDF, position: Point | None, position_name: PositionEnum = PositionEnum.TOP_LEFT, offset: Point = Point(x=0, y=0)) -> Point:
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
            position = Point(x=int(pdf.epw/2), y=10)
        elif position_name == PositionEnum.BOTTOM:
            position = Point(x=int(pdf.epw/2), y=-10)
        elif position_name == PositionEnum.LEFT:
            position = Point(x=10, y=int(pdf.eph/2))
        elif position_name == PositionEnum.RIGHT:
            position = Point(x=-15, y=int(pdf.eph/2))
        elif position_name == PositionEnum.CENTER:
            position = Point(x=int(pdf.epw/2), y=int(pdf.eph/2))
        else:
            raise ValueError(f"Invalid position name: {position_name}")
    return Point(x=(position.x + offset.x), y=(position.y + offset.y))

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
    position_offset: Point = Field(default=Point(x=0,y=0))

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
        img = PILImage.open(self.image).convert('RGBA')
        if self.angle:
            img = img.rotate(self.angle)
        pdf.image(img, w=img.width*self.scale, h=img.height*self.scale)
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
    input_stamp: Path | str = Field(...)

    def to_pdf(self) -> PdfReader:
        return PdfReader(self.input_stamp)


class PdfTransform:
    def split(self) -> list[PDFOutput]:
        raise NotImplementedError("Not implemented yet")

    def img_to_pdf(self, image: Image | Path | str, output: PDFOutput, scale: float) -> PDFOutput:
        pdf = FPDF()
        pdf.add_page()
        if isinstance(image, (Path, str)):
            image = PILImage.open(image)
        pdf.image(image, w=image.width*scale, h=image.height*scale)
        imgpdf = PdfReader(BytesIO(pdf.output()))
        writer = PdfWriter()
        writer.append(imgpdf)
        success, _ = writer.write(output)
        if not success:
            raise ValueError("Failed to write the output file")

        return output

    def merge(self, files: Sequence[PDFInput], output: PDFOutput, names: list[str] = []) -> PDFOutput:
        merger = PdfWriter()
        if not files:
            raise ValueError("No files to merge")
        if len(names) == len(files):
            for f, n in zip(files, names):
                merger.append(f, outline_item=n)
        else:
            for f in files:
                merger.append(f)
        merger.write(output)
        merger.close()
        return output

    def stamp(self, fileinput: PDFInput, output: PDFOutput, stamp: StampPdf | StampText | StampImage , pages: set[int] | None = None) -> PDFOutput:
        """
        Stamp a PDF file with a text string.

        :param file: the input PDF file
        :param output: the output PDF file
        :param stamp: the stamp to apply
        :param pages: the pages to stamp, if None, all pages will be stamped
        """
        writer = PdfWriter(clone_from=fileinput)
        p = 0
        stamp_pdf = stamp.to_pdf().pages[0]
        for page in writer.pages:
            if pages and  p not in pages:
                continue
            page.merge_page(stamp_pdf, over=stamp.over)
        success, _ = writer.write(output)
        if not success:
            raise ValueError("Failed to write the output file")
        return output
