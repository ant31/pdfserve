import json
import os
import urllib.parse
from typing import Any, Optional, Type

import pytest
import requests
from fastapi.testclient import TestClient

import pdfserve.config
import pdfserve.version
from pdfserve.server.server import serve

DEFAULT_PREFIX = "http://localhost:5000"


class TestServer:
    @property
    def token(self) -> str:
        return "changeme"

    def headers(self) -> dict[str, str]:
        d = {
            "Content-Type": "application/json",
            "admin-token": "dummy_key",
        }
        if self.token:
            d["token"] = self.token
        return d

    class Client(object):
        def __init__(self, client: requests.Session, headers: Optional[dict[str, str]] = None) -> None:
            self.client = client
            self.headers = headers

        def _request(self, method: str, path: str, params: dict[str, str], body: dict[str, Any]) -> requests.Response:
            if params:
                path = path + "?" + urllib.parse.urlencode(params)

            return getattr(self.client, method)(
                path,
                data=json.dumps(body, sort_keys=True, default=str),
                headers=self.headers,
            )

        def get(self, path: str, params: dict[str, str] = {}, body: dict[str, Any] = {}) -> requests.Response:
            path = path + "?" + urllib.parse.urlencode(params)
            return self.client.get(path, headers=self.headers)

        def delete(self, path: str, params: dict[str, str] = {}, body: dict[str, Any] = {}) -> requests.Response:
            path = path + "?" + urllib.parse.urlencode(params)
            return self.client.delete(path, json=body)

        def post(self, path: str, params: dict[str, str] = {}, body: dict[str, Any] = {}) -> requests.Response:
            return self._request("post", path, params, body)

    def json(self, res: requests.Response) -> Any:
        return res.json()

    def _url_for(self, path: str) -> str:
        return DEFAULT_PREFIX + self.api_prefix + path

    @property
    def api_prefix(self) -> str:
        return os.getenv("GIROFUNNEL_API_PREFIX", "")

    @pytest.fixture(autouse=True)
    def client(self) -> requests.Session:
        client = TestClient(serve())
        return client

    def test_root(self, client: requests.Session) -> None:
        url = self._url_for("")
        res = self.Client(client, self.headers()).get(url)
        assert res.status_code == 200
        assert self.json(res) == {"version": pdfserve.version.VERSION.app_version}

    def test_version(self, client: requests.Session) -> None:
        url = self._url_for("")
        res = self.Client(client, self.headers()).get(url)
        assert res.status_code == 200
        assert self.json(res) == {"version": pdfserve.version.VERSION.app_version}

    def test_error(self, client: requests.Session) -> None:
        url = self._url_for("/debug/error")
        res = self.Client(client, self.headers()).get(url)
        assert res.status_code == 403

    def test_404(self, client: requests.Session) -> None:
        url = self._url_for("/unknown")
        res = self.Client(client, self.headers()).get(url)
        assert res.status_code == 404

    def test_500(self, client: requests.Session) -> None:
        url = self._url_for("/debug/error_uncatched")

        res = self.Client(client, self.headers()).get(url)
        assert res.status_code == 500


BaseTestServer = TestServer


@pytest.mark.usefixtures("live_server")
class LiveTestServer(BaseTestServer):
    class Client(object):
        def __init__(
            self,
            client: requests.Session = requests.session(),
            headers: dict[str, str] = {},
        ) -> None:
            self.client = client
            self.headers = headers

        def _request(self, method: str, path: str, params: dict[str, str], body: dict[str, Any]) -> requests.Response:
            return getattr(self.client, method)(
                path,
                params=params,
                data=json.dumps(body, sort_keys=True, default=str),
                headers=self.headers,
            )

        def get(self, path: str, params: dict[str, str] = {}, body: dict[str, Any] = {}) -> requests.Response:
            return self._request("get", path, params, body)

        def delete(self, path: str, params: dict[str, str] = {}, body: dict[str, Any] = {}) -> requests.Response:
            return self._request("delete", path, params, body)

        def post(self, path: str, params: dict[str, str] = {}, body: dict[str, Any] = {}) -> requests.Response:
            return self._request("post", path, params, body)

    def _url_for(self, path: str) -> str:
        # FIXME: not sure what this line is trying to do; there is nothing called `request` in this file.
        return request.url_root + self.api_prefix + path

    def json(self, res: requests.Response) -> Any:
        return res.json()


def get_server_class() -> Type[BaseTestServer]:
    if os.getenv("GIROFUNNEL_TEST_LIVESERVER", "false") == "true":
        return LiveTestServer
    else:
        return BaseTestServer


ServerTest = get_server_class()
