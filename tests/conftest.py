from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        debug=False,
        storage_dir=tmp_path / "storage",
        ai_mode="demo",
        image_provider="placeholder",
        image_width=512,
        image_height=512,
        enable_test_image_endpoint=True,
    )


@pytest.fixture()
def client(settings: Settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
