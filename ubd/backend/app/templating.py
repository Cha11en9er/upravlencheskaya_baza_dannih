"""Jinja2-шаблонизатор и пути фронтенда (отдельный модуль, чтобы не было циклических импортов)."""
from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

ROOT_DIR = Path(__file__).resolve().parent.parent.parent  # ubd/
FRONTEND = ROOT_DIR / "frontend"

templates = Jinja2Templates(directory=str(FRONTEND / "templates"))
templates.env.filters["money"] = lambda v: "" if v in (None, "") else f"{int(v):,}".replace(",", " ")
templates.env.filters["dt"] = lambda v: v.strftime("%d.%m.%Y") if v else ""


def access_level_for(user, block: str) -> str:
    """Уровень доступа пользователя к блоку — для навигации и плиток."""
    if user is None:
        return "none"
    if user.role == "Администратор":
        return "edit"
    from . import permissions
    return permissions.access_level(user.block_access, block)


templates.env.globals["access_level"] = access_level_for
