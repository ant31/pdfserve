#!/usr/bin/env python3
import os

from pdfserve.config import GConfig


def test_config_test_env():
    assert GConfig().app.env == "test"


def test_config_fields():
    assert GConfig().sentry.dsn == None
    assert GConfig().temporalio.host == "localhost:7233"
    assert GConfig().server.port == 8080
    assert GConfig().logging.level == "info"
    assert GConfig().conf.app.env == "test"


def test_config_reinit():
    conf = GConfig().dump()
    GConfig.reinit()
    assert GConfig().dump() == conf
    # Changes are ignored without reinit
    GConfig("tests/data/config-2.yaml")
    assert GConfig().dump() == conf
    # Changes are applied after reinit
    GConfig.reinit()
    GConfig("tests/data/config-2.yaml")
    assert GConfig().dump() != conf


def test_config_path_load():
    GConfig.reinit()
    GConfig("tests/data/config-2.yaml")
    assert GConfig().app.env == "test-2"


def test_config_path_load_from_env(monkeypatch):
    GConfig.reinit()
    monkeypatch.setattr(os, "environ", {"PDFSERVE_CONFIG": "tests/data/config-2.yaml"})
    assert GConfig().app.env == "test-2"


def test_config_path_failed_path_fallback():
    GConfig.reinit()
    GConfig("tests/data/config-dontexist.yaml")
    assert GConfig().app.env == "dev"
