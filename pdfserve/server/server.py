from ant31box.server.server import Server, serve_from_config
from fastapi import FastAPI

from pdfserve.config import config


class PdfServer(Server):
    _routers: set[str] = {"pdfserve.server.api.pdf:router", "pdfserve.server.api.ocr:router"}


# override this method to use a different server class/config
def serve() -> FastAPI:
    return serve_from_config(config(), PdfServer)
