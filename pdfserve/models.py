# pylint: disable=no-name-in-module
# pylint: disable=no-self-argument
# pylint: disable=too-few-public-methods
import datetime
import hashlib
import hmac
import logging
import uuid
from enum import StrEnum
from typing import Any, Literal, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


class DefaultType(StrEnum):
    NO_DEFAULT = "__no_default__"
    NOT_FOUND = "__not_found__"


class S3Dest(BaseModel):
    bucket: str = Field("...")
    path: str = Field("...")
    url: str = Field(default="")

class Job(BaseModel):
    uuid: str = Field(...)
    name: str = Field(...)
    status: str | None = Field(default=None)
    result: dict = Field(default={})

class JobList(BaseModel):
    jobs: list[Job] = Field([])


class AsyncResponse(BaseModel):
    payload: JobList = Field(default=JobList(jobs=[]))
    signature: str | None = Field(default=None)

    def gen_signature(self):
        self.signature = hmac.new(
            self.secret_key, self.payload.model_dump_json().encode(), hashlib.sha256
        ).hexdigest()
        return self.signature

    def check_signature(self):
        expect = hmac.new(
            self.secret_key, self.payload.model_dump_json().encode(), hashlib.sha256
        ).hexdigest()
        if expect != self.signature:
            return False
        return True

    @property
    def secret_key(self):
        return b"NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j"
