import hashlib
import logging
import tempfile
from email.message import EmailMessage
from io import BytesIO
from pathlib import PurePath
from urllib.parse import unquote, urlparse

import aiofiles
import aioshutil as shutil
from pydantic import BaseModel

from pdfserve.client.base import BaseClient, ClientConfig

# create a temporary directory using the context manager


logger: logging.Logger = logging.getLogger(__name__)


class FileDownload(BaseModel):
    filename: str | None = None
    content: BytesIO | None = None
    path: PurePath | str | None = None


class DownloadClient(BaseClient):

    @classmethod
    def default_config(cls) -> ClientConfig:
        return ClientConfig(endpoint="http://localhost:8080", client_name="filedl", verify_tls=True)

    def build_path(self, content: bytes, source_path: str, dest_dir: str, filename: str = "") -> str:

        if not filename:
            path = PurePath(source_path)
            hashsha = hashlib.sha256(content)
            suffix = path.suffix
            filename = hashsha.hexdigest() + suffix
        return str(PurePath(dest_dir).joinpath(filename))

    async def copy_local_file(
        self, source_path: str, dest_dir: str, sha_name: bool = False, output: str | BytesIO = ""
    ) -> FileDownload:
        filename = ""

        # Read input
        async with aiofiles.open(source_path, "rb") as fopen:
            content = await fopen.read()

        # Write output
        # if output is a BytesIO, write the content to it and return it
        if output and isinstance(output, BytesIO):
            output.write(content)
            return FileDownload(content=output, filename=filename)

        # if output is a string, write the content to the file and return
        elif output and isinstance(output, str):
            dest_path = output
        else:
            if not sha_name:
                filename = PurePath(source_path).name
            dest_path = self.build_path(content, source_path, dest_dir, filename)
        await shutil.copyfile(source_path, dest_path)
        return FileDownload(filename=filename, path=dest_path, content=BytesIO(content))

    def headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Accept": "*/*",
        }
        if extra is not None:
            headers.update(extra)
        return super().headers(extra=headers)

    async def download_file(
        self, url: str, source_path: str, dest_dir: str, sha_name: bool = False, output: str | BytesIO = ""
    ) -> FileDownload:
        resp = await self.session.get(url, headers=self.headers())
        resp.raise_for_status()
        content_disposition = resp.headers.get("Content-Disposition")
        filename: str = ""

        if not sha_name:
            if content_disposition:
                msg = EmailMessage()
                msg["Content-Disposition"] = content_disposition
                _, params = msg.get_content_type(), msg["Content-Disposition"].params
                filename = params.get("filename", "")
            if not filename:
                filename = unquote(PurePath(source_path).name)

        content = await resp.content.read()

        if output and isinstance(output, BytesIO):
            output.write(content)
            fd = FileDownload(content=output, filename=filename)
            return fd
        elif output and isinstance(output, str):
            dest_path = output
        else:
            dest_path = self.build_path(content, source_path, dest_dir, filename)
        async with aiofiles.open(dest_path, "wb") as fopen:
            await fopen.write(content)
        fd = FileDownload(filename=filename, path=dest_path)
        return fd

    async def download(self, source: str, dest_dir: str = "") -> FileDownload:
        """
        Determine the protocol to fetch the document:
        file://,
        http://,
        s3:// ...
        """
        if not dest_dir:
            dest_dir = tempfile.mkdtemp()
        parsedurl = urlparse(source)
        logger.info("download %s, %s", source, parsedurl.path)
        if parsedurl.scheme in ["file", ""]:
            return await self.copy_local_file(parsedurl.path, dest_dir)
        if parsedurl.scheme in ["http", "https"]:
            return await self.download_file(source, parsedurl.path, dest_dir)

        raise AttributeError(f"Unsupported file source: scheme={parsedurl.scheme} - path={parsedurl.path}")
