import os

import pytest
from pdfserve.config import GConfig
LOCAL_DIR = os.path.dirname(__file__)

@pytest.fixture
def app():
    from pdfserve.api.app import create_app

    app = create_app().app
    return app

@pytest.fixture(autouse=True)
def reset_config():
    GConfig.reinit()
    GConfig()
