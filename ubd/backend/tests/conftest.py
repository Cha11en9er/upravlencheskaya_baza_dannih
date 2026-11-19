"""Общая обвязка тестов: изолированная SQLite-база на время тестового прогона.

Важно: у каждого клиента своя cookie-кува (logout в одном тесте не ломает другие).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP_DB = (Path(tempfile.gettempdir()) / "ubd_test.db").as_posix()
os.environ["UBD_DB_URL"] = f"sqlite:///{_TMP_DB}"
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _logged_in(email: str, password: str) -> TestClient:
    c = TestClient(app)  # startup идемпотентен: create_all + сид при пустой базе
    resp = c.post("/login", data={"email": email, "password": password}, follow_redirects=False)
    assert resp.status_code == 303, f"логин {email} должен пройти"
    return c


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin_client():
    c = _logged_in("admin@ubd.local", "admin123")
    yield c
    c.close()


@pytest.fixture(scope="session")
def fin_client():
    c = _logged_in("fin@ubd.local", "user123")
    yield c
    c.close()
