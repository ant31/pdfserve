import asyncio
import hashlib
import logging
import uuid
from email.message import EmailMessage
from io import IOBase
from pathlib import Path, PurePath
from typing import Literal
from urllib.parse import unquote, urlparse

import aiofiles
import aioshutil as shutil
from pydantic import BaseModel, ConfigDict, Field

from pdfserve.client.base import BaseClient, ClientConfig

# create a temporary directory using the context manager


logger: logging.Logger = logging.getLogger(__name__)


class FileInfo(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    filename: str = Field(default="")
    content: IOBase | None = Field(default=None)
    path: PurePath | str | None = Field(default=None)
    source: str | Path | None = Field(default=None)
    metadata: dict[str, str] | None = Field(default=None)


class DownloadClient(BaseClient):

    @classmethod
    def default_config(cls) -> ClientConfig:
        return ClientConfig(endpoint="http://localhost:8080", client_name="filedl", verify_tls=True)

    def _gen_sha(self, content: bytes, source_path: str, dest_dir: str, filename: str) -> str:
        path = PurePath(source_path)
        hashsha = hashlib.sha256(content)
        suffix = path.suffix
        filename = hashsha.hexdigest() + suffix
        return str(PurePath(dest_dir).joinpath(filename))

    async def copy_local_file(
        self, source_path: str, dest_dir: str | Path = "", output: str | Path | IOBase = ""
    ) -> FileInfo:

        filename = PurePath(source_path).name
        # Write output
        # if output is a IOBase, write the content to it and return it
        if output and isinstance(output, IOBase):
            # Read input
            async with aiofiles.open(source_path, "rb") as fopen:
                output.write(await fopen.read())
                return FileInfo(content=output, filename=filename, source=source_path)

        # if output is a string, write the content to that file and return
        elif output and isinstance(output, (Path, str)):
            dest_path = output
        else:
            dest_path = PurePath(dest_dir).joinpath(filename)
        await shutil.copyfile(source_path, dest_path)
        return FileInfo(filename=filename, path=dest_path, source=source_path)

    def headers(
        self, content_type: Literal["json", "form"] | str | None = None, extra: dict[str, str] | None = None
    ) -> dict[str, str]:
        headers = {
            "Accept": "*/*",
        }
        if extra is not None:
            headers.update(extra)
        return super().headers(content_type=content_type, extra=headers)

    async def download_file(
        self, url: str, source_path: str, dest_dir: str | Path = "", output: str | Path | IOBase = ""
    ) -> FileInfo:
        resp = await self.session.get(url, headers=self.headers())
        resp.raise_for_status()

        filename: str = ""
        logger.info("Downloaded file to dir: %s", dest_dir)
        content_disposition = resp.headers.get("Content-Disposition")
        if content_disposition:
            msg = EmailMessage()
            msg["Content-Disposition"] = content_disposition
            _, params = msg.get_content_type(), msg["Content-Disposition"].params
            filename = params.get("filename", "")
        if not filename:
            filename = unquote(PurePath(source_path).name)
        content = await resp.content.read()

        if output and isinstance(output, IOBase):
            output.write(content)
            fd = FileInfo(content=output, filename=filename, source=url)
            return fd
        if output and isinstance(output, (Path, str)) and str(output) != "" and str(output) != ".":
            dest_path = output
        else:
            if filename == "":
                filename = uuid.uuid4().hex
            dest_path = PurePath(dest_dir).joinpath(f"{uuid.uuid4().hex}-{filename}")
        logger.info("Downloaded file to %s", dest_path)
        async with aiofiles.open(dest_path, "wb") as fopen:
            await fopen.write(content)
        fd = FileInfo(filename=filename, path=dest_path, source=url)
        return fd

    async def download(self, source: str, dest_dir: str | Path = "", output: str | Path | IOBase = "") -> FileInfo:
        """
        Determine the protocol to fetch the document:
        file://,
        http://,
        s3:// ...
        """
        parsedurl = urlparse(source)
        logger.info("download %s, %s", source, parsedurl.path)
        if parsedurl.scheme in ["file", ""]:
            return await self.copy_local_file(source_path=parsedurl.path, dest_dir=dest_dir, output=output)
        if parsedurl.scheme in ["http", "https"]:
            return await self.download_file(url=source, source_path=parsedurl.path, dest_dir=dest_dir, output=output)

        raise AttributeError(f"Unsupported file source: scheme={parsedurl.scheme} - path={parsedurl.path}")
