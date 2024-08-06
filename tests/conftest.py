import os

import pytest

from pdfserve.config import config

LOCAL_DIR = os.path.dirname(__file__)


@pytest.fixture()
def testdir():
    return LOCAL_DIR


@pytest.fixture(autouse=True)
def reset_config():
    config(reload=True)
