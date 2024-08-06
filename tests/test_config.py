#!/usr/bin/env python3
import os

from pdfserve.config import config


def test_config_test_env():
    assert config().app.env == "test"


def test_config_fields():
    assert config().sentry.dsn == None
    assert config().server.port == 8080
    assert config().logging.level == "info"
    assert config().conf.app.env == "test"


def test_config_reinit():
    conf = config().dump()
    assert config().dump() == conf
    # Changes are ignored without reinit
    assert config("tests/data/config-2.yaml").dump() == conf
    # Changes are applied after reinit
    config("tests/data/config-2.yaml", reload=True)
    assert config().dump() != conf


def test_config_path_load():
    config("tests/data/config-2.yaml", reload=True)
    assert config().app.env == "test-2"


def test_config_path_load_from_env(monkeypatch):
    monkeypatch.setattr(os, "environ", {"PDFSERVE_CONFIG": "tests/data/config-2.yaml"})
    assert config(reload=True).app.env == "test-2"


def test_config_path_failed_path_fallback():
    config("tests/data/config-dontexist.yaml", reload=True)
    assert config().app.env == "dev"
