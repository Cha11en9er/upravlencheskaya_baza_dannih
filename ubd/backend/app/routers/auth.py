"""Вход/выход (ТЗ 2.1.1).

POST /login не принимает Request вместе с Form: в FastAPI 0.165 + future annotations
такая комбинация ломает разбор параметров. Ошибка входа передаётся redirect'ом
на /login?error=1 (PRG-паттерн).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import COOKIE_NAME, get_current_user
from ..models import User
from ..security import create_token, verify_password
from ..templating import templates

router = APIRouter()


@router.get("/login")
def login_page(request: Request, user: User | None = Depends(get_current_user)):
    if user is not None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "login.html", {"error": "Неверный email или пароль" if request.query_params.get("error") else ""})


@router.post("/login")
def login(db: Session = Depends(get_db), email: str = Form(""), password: str = Form("")):
    user = db.execute(select(User).where(User.email == email.strip().lower())).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        return RedirectResponse("/login?error=1", status_code=303)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(COOKIE_NAME, create_token(user.id, user.email), httponly=True,
                    samesite="lax", max_age=settings.token_expire_hours * 3600)
    return resp


@router.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp
