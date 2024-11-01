#!/usr/bin/env python3
import asyncio
import logging
import re
import tempfile
import uuid
from enum import StrEnum
from io import BytesIO, IOBase
from pathlib import Path
from typing import IO, Any, BinaryIO, Literal, Sequence, TypeAlias, cast
from urllib.parse import urlparse

import PIL.Image
from ant31box.clients import filedl_client
from fpdf import FPDF
from PIL.Image import Image
from PIL.ImageOps import contain
from pillow_heif import register_heif_opener
from pydantic import BaseModel, ConfigDict, Field, RootModel, field_serializer, field_validator  # , model_serializer
from pypdf import PdfReader, PdfWriter

register_heif_opener()
StreamOrPath: TypeAlias = Path | str | BinaryIO | IO[Any]
PDFInput: TypeAlias = IOBase | StreamOrPath
PDFOutput: TypeAlias = IOBase | StreamOrPath

logger: logging.Logger = logging.getLogger(__name__)

A4DPI: dict[int, tuple[int, int]] = {  # A4 size in pixels at N DPI
    # 72 DPI
    72: (595, 842),
    96: (794, 1123),
    150: (1240, 1754),
    300: (2480, 3508),
    # 96 DPI
    # 150 DPI
    # 300 DPI
}


def userspace_to_mm(val) -> float:
    """Userspace to mm conversion
    1 userspace = 1/72 inch
    1 inch = 25.4 mm
    """
    return val * 0.352777777777777777777777777778


class PdfFileInfo(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    filename: str = Field(default="", description="Name of the pdf")
    content: PDFInput | None = Field(default=None, exclude=True, description="Initial input to create the pdf")
    path: Path = Field(default=None, description="Path of the pdf on disk")
    source: Path | str | None = Field(default=None, description="Source of the initial file")
    image: Image | None = Field(default=None, exclude=True, description="Image to convert to PDF")
    scale: float = Field(default=1)
    rotate: int = Field(default=0)
    pdf: PDFInput | None = Field(
        default=None,
        exclude=True,
        description="PDF content after processing the 'content' or 'image'. Either a file or BytesIO",
    )


# pylint: disable=invalid-name
class Color(RootModel):
    model_config = ConfigDict(validate_assignment=True)

    root: tuple[int, int, int] = Field(default=(255, 0, 0), validate_default=True)

    @property
    def r(self) -> int:
        return self.root[0]

    @property
    def g(self) -> int:
        return self.root[1]

    @property
    def b(self) -> int:
        return self.root[2]

    @b.setter
    def b(self, value: int) -> None:
        self.root = (self.r, self.g, value)

    @g.setter
    def g(self, value: int) -> None:
        self.root = (self.r, value, self.b)

    @r.setter
    def r(self, value: int) -> None:
        self.root = (value, self.g, self.b)

    @field_validator("root", mode="before")
    def rgbtubple(cls, root: str | tuple[int, int, int]) -> tuple[int, int, int]:
        if isinstance(root, str):
            reg = r"^ *(-?\d{1,3})[, ] *(-?\d{1,3})[, ] *(-?\d{1,3}) *$"
            search = re.search(reg, root)
            if search is None or len(search.groups()) != 3:
                raise ValueError(f"Invalid color format {root}, must be 'r,g,b' or 'r g b'")
            root = cast(tuple[int, int, int], tuple(int(v) for v in search.groups()[0:3]))
        for v in root:
            if v > 255:
                raise ValueError(f"Invalid color value {v} (>255) in {root}")
        return root

    @field_serializer("root", when_used="json")
    def serialize_rgb(self, rgb):
        return ",".join([str(v) for v in rgb])


class Point(RootModel):
    root: tuple[int, int] = Field(default=(0, 0), validate_default=True)

    @property
    def x(self) -> int:
        return self.root[0]

    @property
    def y(self) -> int:
        return self.root[1]

    @x.setter
    def x(self, value: int) -> None:
        self.root = (value, self.y)

    @y.setter
    def y(self, value: int) -> None:
        self.root = (self.x, value)

    @field_validator("root", mode="before")
    def pos(cls, pos: str | tuple[int, int]) -> tuple[int, int]:
        if isinstance(pos, str):
            reg = r"^ *(-?\d+)[, ] *(-?\d+) *$"
            search = re.search(reg, pos)
            if search is None or len(search.groups()) != 2:
                raise ValueError(f"Invalid Point format {pos}: must be 'x,y' or 'x y'")
            pos = cast(tuple[int, int], tuple(int(v) for v in search.groups()[0:2]))
        return pos

    @field_serializer("root", when_used="json")
    def serialize_pos(self, pos):
        return ",".join([str(v) for v in pos])


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
    offset: Point = Point((0, 0)),
) -> Point:
    if not position:
        if position_name == PositionEnum.TOP_LEFT:
            position = Point((10, 10))
        elif position_name == PositionEnum.TOP_RIGHT:
            position = Point((-15, 10))
        elif position_name == PositionEnum.BOTTOM_LEFT:
            position = Point((10, -10))
        elif position_name == PositionEnum.BOTTOM_RIGHT:
            position = Point((-15, -10))
        elif position_name == PositionEnum.TOP:
            position = Point((int(pdf.epw / 2), 10))
        elif position_name == PositionEnum.BOTTOM:
            position = Point((int(pdf.epw / 2), -10))
        elif position_name == PositionEnum.LEFT:
            position = Point((10, int(pdf.eph / 2)))
        elif position_name == PositionEnum.RIGHT:
            position = Point((-15, int(pdf.eph / 2)))
        elif position_name == PositionEnum.CENTER:
            position = Point((int(pdf.epw / 2), int(pdf.eph / 2)))
        else:
            raise ValueError(f"Invalid position name: {position_name}")
    return Point((position.x + offset.x, position.y + offset.y))


class BaseStamp(BaseModel):
    over: bool = Field(default=False)


class BaseCustomStamp(BaseStamp):
    page_format: tuple[float, float] | Literal["a3", "a4", "a5", "letter", "legal"] = Field(default="a4")
    opacity: float = Field(default=1.0)
    border: bool = Field(default=False)
    border_width: int = Field(default=1)
    background: bool = Field(default=False)
    background_color: Color = Field(default=Color((255, 255, 255)))
    position: Point | None = Field(default=None)
    position_name: PositionEnum = Field(default=PositionEnum.TOP_LEFT)
    position_offset: Point = Field(default=Point((0, 0)))

    def get_position(self, pdf: FPDF) -> Point:
        return get_position(pdf, self.position, self.position_name, self.position_offset)

    def render_pdf(self, pdf: FPDF) -> FPDF:
        return pdf

    def to_pdf(
        self, page_format: tuple[float, float] | Literal["a3", "a4", "a5", "letter", "legal"] | None = None
    ) -> PdfReader:
        pdf = FPDF()
        if page_format is not None:
            pdf.add_page(format=page_format)
        else:
            pdf.add_page(format=self.page_format)
        position = self.get_position(pdf)
        if self.background:
            pdf.set_fill_color(r=self.background_color.r, g=self.background_color.g, b=self.background_color.b)
        pdf.set_xy(position.x, position.y)
        with pdf.local_context(fill_opacity=self.opacity, stroke_opacity=self.opacity):
            self.render_pdf(pdf)
        return PdfReader(BytesIO(pdf.output()))


class StampImage(BaseCustomStamp):
    # attribute not exported
    _image: IOBase | BinaryIO | Path | str | None = None
    image: Path | str | None = Field(
        default=None,
        description="Path on disk to an image. Use load_image to load/download the image first if required",
    )
    angle: int = Field(default=0)
    scale: float = Field(default=1)

    async def load_image(
        self, image: IOBase | BinaryIO | Path | str, tmpdir=""
    ) -> IOBase | BinaryIO | Path | str | None:
        """
        Download the image if the input is a URL
        """
        if isinstance(image, str):
            parsedurl = urlparse(image)
            if parsedurl.scheme in ["http", "https"]:
                with tempfile.SpooledTemporaryFile(dir=tmpdir) as tmp:
                    finfo = await filedl_client().download(str(image), output=tmp)
                    if finfo.content:
                        image = finfo.content
                    elif finfo.path:
                        image = str(finfo.path)
                    else:
                        raise ValueError(f"Invalid file: {finfo}")
        self._image = image
        return image

    def render_pdf(self, pdf: FPDF) -> FPDF:
        image = self.image or self._image
        if image is None:
            raise ValueError("No image to stamp")
        img = PIL.Image.open(image).convert("RGB")
        if self.angle:
            img = img.rotate(self.angle)
        if self.scale != 1:
            pdf.image(img, w=img.width * self.scale, h=img.height * self.scale)
        else:
            pdf.image(img)
        return pdf


class StampText(BaseCustomStamp):
    text: str = Field(...)
    font: str = Field(default="Helvetica")
    size: int = Field(default=16)
    color: Color = Field(default=Color((255, 0, 0)))

    def render_pdf(self, pdf: FPDF) -> FPDF:
        pdf.set_font(self.font, size=self.size)
        pdf.set_text_color(r=self.color.r, g=self.color.g, b=self.color.b)
        pdf.cell(text=self.text, border=self.border, fill=self.background)  # pyre-fixme[28]
        return pdf


class StampPdf(BaseStamp):
    """
    Stamp a PDF file with another PDF file.
    No modification is done to the original file and stamp file, they are just merged together.
    """

    input_stamp: Path | str = Field(...)

    def to_pdf(
        self, page_format: tuple[float, float] | Literal["a3", "a4", "a5", "letter", "legal"] | None = None
    ) -> PdfReader:
        _ = page_format
        return PdfReader(self.input_stamp)


class PdfTransform:
    def __init__(
        self,
        files: Sequence[PDFInput | PdfFileInfo | Image],
        dest_dir: str = "",
        tmpdir: str | None = None,
        use_temporary: bool = True,
        dpi: int = 96,
    ):
        self.dpi = dpi
        self._input_files = files
        self.dest_dir = dest_dir
        self.tmpdir = tmpdir
        self.use_temporary = use_temporary
        self._loaded = False
        self._files = []

    def reload(self):
        self._files = []

    @property
    async def files(self) -> Sequence[PdfFileInfo]:
        if not self._loaded:
            self._files = await self.load_files(
                files=self._input_files, dest_dir=self.dest_dir, use_temporary=self.use_temporary
            )
            self._loaded = True
        return self._files

    def set_files(self, files: Sequence[PDFInput | PdfFileInfo | Image]):
        self._input_files = files
        self._loaded = False

    def _img_filename(self, img: Image) -> str:
        if hasattr(img, "filename"):
            return img.filename  # pyre-fixme[16] # type: ignore
        return ""

    async def load(
        self, fileinput: PDFInput | PdfFileInfo | Image, dest_dir: str = "", use_temporary: bool = True
    ) -> PdfFileInfo:
        if isinstance(fileinput, (str, Path)):
            info = await self.download_file(fileinput, dest_dir=dest_dir, use_temporary=use_temporary)
        elif isinstance(fileinput, Image):
            info = PdfFileInfo(
                filename=self._img_filename(fileinput), source=self._img_filename(fileinput), image=fileinput
            )
        elif isinstance(fileinput, IOBase):
            info = PdfFileInfo(filename="", content=fileinput)
        elif isinstance(fileinput, PdfFileInfo):
            info = await self.load_image(fileinput)
        else:
            raise ValueError(f"Invalid file type: {type(fileinput)}")

        if not info.pdf:
            if info.content:
                info.pdf = info.content
            elif info.path:
                info.pdf = info.path
        if info.pdf is None:
            raise ValueError(f"Invalid file: {info}, missing content or path or pdf")
        return info

    async def download_file(self, source: str | Path, dest_dir: str = "", use_temporary: bool = True) -> PdfFileInfo:
        tmp = Path("")
        if use_temporary:
            tmp = tempfile.SpooledTemporaryFile(dir=self.tmpdir)  # pylint: disable=consider-using-with
        finfo = await filedl_client().download(str(source), dest_dir=dest_dir, output=tmp)
        p = PdfFileInfo(
            filename=str(finfo.filename),
            source=finfo.source,
            path=Path(str(finfo.path)),
            content=finfo.content,
            image=None,
        )
        return await self.load_image(p)

    async def load_image(self, pdfinfo: PdfFileInfo) -> PdfFileInfo:
        # skip pdf or if image is already loaded
        if Path(pdfinfo.filename).suffix == ".pdf" or pdfinfo.pdf:
            return pdfinfo
        try:
            if pdfinfo.content:
                pdfinfo.image = PIL.Image.open(pdfinfo.content)  # type: ignore
            else:
                pdfinfo.image = PIL.Image.open(pdfinfo.path)  # type: ignore
        except PIL.UnidentifiedImageError as e:
            # Skip non-image files
            logger.debug("Failed to open image: %s", e)
        if pdfinfo.image:
            pdfinfo.pdf = self._img_to_pdf(pdfinfo.image, None, scale=pdfinfo.scale, dpi=self.dpi)
        return pdfinfo

    async def load_files(
        self, files: Sequence[PDFInput | PdfFileInfo | Image], dest_dir: str = "", use_temporary: bool = True
    ) -> Sequence[PdfFileInfo]:
        # @TODO user worker pool/deque
        res = []
        n = 5
        split_list = [files[i * n : (i + 1) * n] for i in range((len(files) + n - 1) // n)]
        for split_files in split_list:
            res.append(
                await asyncio.gather(
                    *[self.load(f, dest_dir=dest_dir, use_temporary=use_temporary) for f in split_files]
                )
            )
        return [x for subres in res for x in subres]

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

        - **files**: a list of files to merge, can be a list of URL to download the file from
                    or the uploaded file as binary object, or images
        - **name**: the name of the merged file, if not provided, a random name will be generated
        - **outline**: if True, create an outline with the name of the file, if False, no outline will be added
        """
        if not name:
            name = f"merged_{uuid.uuid4()}.pdf"
        contents = [f.pdf for f in await self.files if f.pdf]

        names = outline_items
        if outline and not names:
            names = [str(f.filename) for f in await self.files]
        if not output:
            output = tempfile.SpooledTemporaryFile(dir=self.tmpdir)  # pylint: disable=consider-using-with

        logger.info("Merging: %s, outline: %s", str(contents), names)
        result = self._merge(contents, output=output, names=names)
        if isinstance(output, (str, Path)):
            return PdfFileInfo(filename=Path(output).name, path=Path(output))
        return PdfFileInfo(filename=name, content=result, pdf=result)

    async def img_to_pdf(
        self,
        name: str = "",
        output: PDFOutput | None = None,
    ) -> PdfFileInfo:
        """
        Convert images to pdf.

        It's uses merge method to convert images to pdf.

        - **files**: a list of files to merge, can be a list of URL to download the file
                     from or the uploaded file as binary object, or images
        - **name**: the name of the merged file, if not provided, a random name will be generated
        """
        if not name:
            name = f"img_{uuid.uuid4()}.pdf"
        return await self.merge(name, output, outline=False)

    def split(self) -> list[PDFOutput]:
        raise NotImplementedError("Not implemented yet")

    def _img_to_pdf(self, image: Image | Path | str, output: PDFOutput | None, scale: float = 1, dpi=96) -> PDFOutput:
        pdf = FPDF()
        pdf.add_page()
        if isinstance(image, (Path, str)):
            image = PIL.Image.open(image)
        if scale != 1:
            pdf.image(image, w=image.width * scale, h=image.height * scale, keep_aspect_ratio=True)
        else:
            scale = 0.1
            image = contain(image, A4DPI[dpi])
            pdf.image(image, keep_aspect_ratio=True, h=pdf.eph, w=pdf.epw)
        imgpdf = PdfReader(BytesIO(pdf.output()))
        writer = PdfWriter()
        writer.append(imgpdf)
        if output is None:
            output = tempfile.SpooledTemporaryFile(dir=self.tmpdir)  # pylint: disable=consider-using-with
        success, output = writer.write(cast(StreamOrPath, output))
        if not success and isinstance(output, (str, Path)):
            raise ValueError(f"Failed to write the output file: {output}")
        return output

    def _merge_one_doc(self, merger: PdfWriter, fileinput: PDFInput, outline: str | None = None) -> PdfWriter:
        with tempfile.SpooledTemporaryFile(dir=self.tmpdir) as output:
            merger.write(output)
            m = PdfWriter(clone_from=output)
            try:
                m.append(fileinput, outline_item=outline)
            except AttributeError:
                m = PdfWriter(clone_from=output)
                buf = PdfReader(cast(StreamOrPath, fileinput))
                buf.add_form_topname("f1")
                m.append(fileobj=buf, outline_item=outline)
        return m

    def _merge(self, files: Sequence[PDFInput], output: PDFOutput, names: Sequence[str] | None = None) -> PDFOutput:
        merger = PdfWriter()
        if not files:
            raise ValueError("No files to merge")
        if names and (len(names) == len(files)):
            for f, n in zip(files, names):
                merger = self._merge_one_doc(merger, f, n)
        else:
            for f in files:
                merger = self._merge_one_doc(merger, f)
        _, res = merger.write(cast(StreamOrPath, output))
        return res

    def _prep_outputs(
        self, base_name: Path, n: int, outputs: Sequence[PDFOutput] | None = None, prefix: str = ""
    ) -> tuple[list[Path], list[PDFOutput | None]]:
        names = []
        res_outputs = []
        if not base_name or str(base_name) == ".":
            if outputs and isinstance(outputs[0], (str, Path)):
                base_name = Path(cast(str | Path, outputs[0]))
            else:
                base_name = Path(f"{prefix}_{uuid.uuid4()}.pdf")

        suffix = base_name.suffix
        i = 0
        if outputs:
            for output in outputs:
                # Append name if output is a string or path
                if isinstance(output, (str, Path)):
                    names.append(Path(output))
                elif i == 0:
                    names.append(base_name)
                else:
                    names.append(Path(str(base_name).replace(suffix, f"_{i}{suffix}")))
                res_outputs.append(output)
                i += 1
        name = base_name

        for j in range(i, n):
            if j > 0:
                name = Path(str(base_name).replace(suffix, f"_{j}{suffix}"))
            names.append(name)
            if outputs:
                res_outputs.append(name)
            else:
                res_outputs.append(None)
        return names, res_outputs

    async def stamp(
        self,
        stamp: StampPdf | StampText | StampImage,
        name: str = "",
        outputs: Sequence[PDFOutput] | None = None,
        pages: Sequence[set[int]] | None = None,
    ) -> list[PdfFileInfo]:
        """
        Apply a stamp to all input PDF files.
        returns the list of stamped files.

        - **name**: the name of the merged file, if not provided, a random name will be generated
        - **outputs**: the output files, if not provided, a temporary file will be created.
                       If provided the list len must be the same as the input files
        - **pages**: the pages to stamp, if not provided, all pages will be stamped
        """

        contents = [f.pdf for f in await self.files if f.pdf]

        names, uniq_outputs = self._prep_outputs(Path(name), len(contents), outputs, prefix="stamped")
        logger.info("Stamping: %s, names: %s", str(contents), names)
        if pages and len(contents) != len(pages):
            raise ValueError("Invalid pages, must be the same length as the input files if provided")

        i = 0
        stamp_pages = None
        results = []
        for content in contents:
            output = uniq_outputs[i]
            if output is None:
                output = tempfile.SpooledTemporaryFile(dir=self.tmpdir)  # pylint: disable=consider-using-with
            if pages:
                stamp_pages = pages[i]
            result = self._stamp_one_pdf(content, output, stamp, pages=stamp_pages)
            if isinstance(output, (str, Path)):
                results.append(PdfFileInfo(filename=names[i].name, path=Path(output)))
            else:
                results.append(PdfFileInfo(filename=names[i].name, content=result, pdf=result))
                # output.close()
            i += 1
        return results

    def _stamp_one_pdf(
        self,
        fileinput: PDFInput,
        output: PDFOutput,
        stamp: StampPdf | StampText | StampImage,
        pages: set[int] | None = None,
    ) -> PDFOutput:
        """
        Stamp a PDF file with a text, image or pdf as the stamp

        :param file: the input PDF file
        :param output: the output PDF file
        :param stamp: the stamp to apply
        :param pages: the pages to stamp, if None, all pages will be stamped
        """
        # if not isinstance(output, (str, Path)):
        #     print(output.closed, output.name, output.mode)
        writer = PdfWriter(clone_from=cast(StreamOrPath, fileinput))
        p = 0

        for page in writer.pages:
            if pages and p not in pages:
                continue
            page_format = (userspace_to_mm(page.bleedbox.width), userspace_to_mm(page.bleedbox.height))
            stamp_pdf = stamp.to_pdf(page_format=page_format).pages[0]
            page.merge_page(stamp_pdf, over=stamp.over)
        success, _ = writer.write(cast(StreamOrPath, output))
        if not success and isinstance(output, (str, Path)):
            raise ValueError(f"Failed to write the output file: {output}")

        return output
