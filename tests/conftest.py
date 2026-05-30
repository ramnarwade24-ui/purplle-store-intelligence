from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

# Enable src/ layout imports without requiring an editable install.
repo_root = Path(__file__).resolve().parents[1]
src_root = repo_root / "src"
if str(src_root) not in sys.path:
    sys.path.insert(0, str(src_root))

from storeintel.api.main import create_app


@pytest.fixture
def client(tmp_path: Path):
    db_path = tmp_path / "test.db"
    os.environ["SQLITE_PATH"] = str(db_path)
    os.environ["LOG_JSON"] = "false"
    app = create_app()
    with TestClient(app) as c:
        yield c
