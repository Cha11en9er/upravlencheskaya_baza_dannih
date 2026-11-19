"""Общая обвязка тестов: изолированная SQLite-база на время тестового прогона.

Важно:
- каждый клиент входит в `with TestClient(app)` — только так гарантированно
  выполняется startup (create_all + авто-сид), в новых starlette/httpx2
  TestClient без `with` startup НЕ запускает;
- у каждого клиента своя cookie-кува (logout в одном тесте не ломает другие).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP_DB = (Path(tempfile.gettempdir()) / "ubd_test.db").as_posix()
os.environ["UBD_DB_URL"] = f"sqlite:///{_TMP_DB}"
# тестовые креды — независимо от .env (на сервере пароль админа другой)
os.environ["UBD_ADMIN_EMAIL"] = "admin@ubd.local"
os.environ["UBD_ADMIN_PASSWORD"] = "admin123"
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin_client():
    with TestClient(app) as c:
        resp = c.post("/login", data={"email": "admin@ubd.local", "password": "admin123"},
                      follow_redirects=False)
        assert resp.status_code == 303, "логин админа должен пройти"
        yield c


@pytest.fixture(scope="session")
def fin_client():
    with TestClient(app) as c:
        resp = c.post("/login", data={"email": "fin@ubd.local", "password": "user123"},
                      follow_redirects=False)
        assert resp.status_code == 303, "логин финансиста должен пройти"
        yield c
