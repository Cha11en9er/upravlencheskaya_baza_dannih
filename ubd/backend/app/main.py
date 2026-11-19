"""Точка входа FastAPI УБД. Запуск: uvicorn app.main:app (см. run.bat / README)."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .db import Base, SessionLocal, engine
from .deps import AccessDenied, LoginRequired
from .models import User
from .routers import admin, auth, budget, contractors, contracts, dashboard, payments, reports
from .templating import FRONTEND, templates

app = FastAPI(title="УБД — Управленческая база данных", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=FRONTEND / "static"), name="static")

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(contracts.router)
app.include_router(payments.router)
app.include_router(budget.router)
app.include_router(contractors.router)
app.include_router(reports.router)
app.include_router(admin.router)


@app.exception_handler(LoginRequired)
async def login_required_handler(request: Request, exc: LoginRequired):
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(AccessDenied)
async def access_denied_handler(request: Request, exc: AccessDenied):
    return HTMLResponse(
        f"<h1 style='font-family:sans-serif'>403 — {exc.message}</h1>"
        "<p style='font-family:sans-serif'><a href='/'>На главную</a></p>",
        status_code=403,
    )


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        has_users = db.execute(select(User.id).limit(1)).scalar() is not None
    finally:
        db.close()
    if not has_users:
        from .seed import seed_admin  # локальный импорт, чтобы тесты не тянули сид
        db = SessionLocal()
        try:
            seed_admin(db)
        finally:
            db.close()


from .models import User  # noqa: F811  (переимпорт не нужен, оставлен для читаемости)


def run() -> None:  # pragma: no cover
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":  # pragma: no cover
    run()
