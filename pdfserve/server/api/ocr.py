# pylint: disable=no-name-in-module
# pylint: disable=too-few-public-methods
import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from pdfserve.version import VERSION

router = APIRouter(prefix="/api/v1/ocr", tags=["ocr"])

logger = logging.getLogger(__name__)


class VersionResp(BaseModel):
    version: str = Field(...)


@router.get("/")
async def index():
    return VERSION.to_dict()
