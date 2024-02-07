#!/usr/bin/env python3

import logging
from typing import Any, Literal, cast
from urllib.parse import ParseResult, urlparse

import aiohttp
from pydantic import BaseModel

from pdfserve.version import VERSION

logger = logging.getLogger(__name__)


class ClientConfig(BaseModel):
    endpoint: str = "http://localhost:8080"
    client_name: str = "client"
    verify_tls: bool = True
    session_args: tuple[list, dict[str, Any]] = ([], {})


class SessionMixin:
    _session: aiohttp.ClientSession | None = None
    _config: ClientConfig | None = None

    def __init__(self, config: ClientConfig | None, reload: bool = False) -> None:
        self.__class__.set_config(config=config, reload=reload)

    @classmethod
    def close(cls):
        """
        Close aiohttp.ClientSession.

        This is useful to be called manually in tests if each test when each test uses a new loop. After close, new
        requests will automatically create a new session.

        Note: We need a sync version for `__del__` and `aiohttp.ClientSession.close()` is async even though it doesn't
        have to be.
        """
        if cls._session:
            if not cls._session.closed:
                # Older aiohttp does not have _connector_owner
                if not hasattr(cls._session, "_connector_owner") or cls._session._connector_owner:
                    try:
                        if cls._session._connector:
                            cls._session._connector._close()  # New version returns a coroutine in close() as warning
                    except Exception:
                        if cls._session._connector:
                            cls._session._connector.close()
                cls._session._connector = None
            cls._session = None

    @classmethod
    def default_config(cls) -> ClientConfig:
        return ClientConfig(endpoint="http://localhost:8080", client_name="client", verify_tls=True)

    @classmethod
    def set_config(cls, config: ClientConfig | None, reload: bool = False) -> None:
        if reload or cls._config is None:
            if config == None:
                config = cls.default_config()
            cls._config = config
            cls.close()
        return None

    @property
    def config(self) -> ClientConfig:
        if not self._config:
            self.__class__.set_config(config=None, reload=False)
        return cast(ClientConfig, self._config)

    @property
    def session(self) -> aiohttp.ClientSession:
        """An instance of aiohttp.ClientSession"""
        if not self._session or self._session.closed or not self._session._loop or self._session._loop.is_closed():
            self.__class__._session = aiohttp.ClientSession(*self.config.session_args[0], **self.config.session_args[1])
        return cast(aiohttp.ClientSession, self._session)


class BaseClient(SessionMixin):
    def __init__(self, config: ClientConfig | None = None, reload: bool = False) -> None:
        super().__init__(config=config, reload=reload)
        self.endpoint: ParseResult = self._configure_endpoint(self.config.endpoint)
        self._headers: dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": f"pdfserve-cli/{self.config.client_name}-{VERSION.app_version}",
        }
        self.verify_tls = self.config.verify_tls

    @property
    def ssl_mode(self) -> bool | None:
        return None if self.verify_tls else False

    # pylint: disable=too-many-arguments
    async def log_request(
        self,
        path: str,
        params: dict[str, Any],
        body: dict[str, Any],
        method: str,
        headers: dict[str, str],
        resp: aiohttp.ClientResponse,
    ) -> None:
        raw = await resp.text()
        logger.debug(
            {
                "query": {
                    "params": params,
                    "body": body,
                    "path": path,
                    "method": method,
                    "headers": headers,
                },
                "response": {"status": resp.status, "raw": raw},
            }
        )

    def _url(self, path) -> str:
        """Construct the url from a relative path"""
        return self.endpoint.geturl() + path

    def _configure_endpoint(self, endpoint: str) -> ParseResult:
        return urlparse(endpoint)

    def headers(
        self,
        content_type: Literal["json", "form"] | str | None = None,
        extra: dict[str, str] | None = None,
    ) -> dict[str, str]:
        headers: dict[str, str] = {}
        headers.update(self._headers)

        if content_type == "json":
            headers["Content-Type"] = "application/json"
        elif content_type == "form":
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif content_type:
            headers["Content-Type"] = content_type

        if extra:
            headers.update(extra)

        return headers
