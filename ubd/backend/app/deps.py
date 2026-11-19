"""Зависимости: текущий пользователь, проверка доступа к блокам."""
from __future__ import annotations

from fastapi import Depends, Request

from . import permissions
from .db import get_db
from .models import User
from .security import decode_token
from sqlalchemy.orm import Session

COOKIE_NAME = "ubd_token"


class LoginRequired(Exception):
    """Страница требует входа."""


class AccessDenied(Exception):
    """Нет доступа к блоку/действию (рендерим 403-страницу)."""

    def __init__(self, message: str = "Доступ запрещён"):
        self.message = message


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    user = db.get(User, int(payload.get("sub", 0)))
    if not user or not user.is_active:
        return None
    return user


def page_user(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise LoginRequired()
    return user


def block_level(user: User, block: str) -> str:
    if user.role == "Администратор":
        return permissions.EDIT
    return permissions.access_level(user.block_access, block)


def require_block(block: str, need_edit: bool = False):
    """Фабрика зависимостей: вход + уровень доступа к блоку (ТЗ 1.2 п.2)."""
    def checker(user: User = Depends(page_user)) -> User:
        level = block_level(user, block)
        if level == permissions.NONE:
            raise AccessDenied("Блок недоступен по правам")
        if need_edit and level != permissions.EDIT:
            raise AccessDenied("Блок открыт только на чтение")
        return user
    return checker


def require_admin(user: User = Depends(page_user)) -> User:
    if user.role != "Администратор":
        raise AccessDenied("Только для Администратора")
    return user
