"""Админ-панель (ТЗ 2.1.2): пользователи + права, проекты/объекты, журнал изменений."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_admin
from ..models import ChangeLog, Project, ProjectObject, User
from ..permissions import BLOCKS, EDIT, NONE, READ, default_access_for_role, normalize_access, ROLES
from ..parsing import parse_id
from ..security import hash_password
from ..templating import templates

router = APIRouter(prefix="/admin")
PAGE_SIZE = 80


# ---------- Пользователи ----------

def _user_context(db: Session, user: User, **extra) -> dict:
    ctx = {
        "user": user,
        "roles": ROLES,
        "blocks": BLOCKS,
        "levels": [EDIT, READ, NONE],
        "users": db.execute(select(User).order_by(User.id)).scalars().all(),
    }
    ctx.update(extra)
    return ctx


@router.get("/users")
def users_page(request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "admin/users.html", _user_context(
        db, user, edit_user=None, msg=request.query_params.get("msg", "")))


@router.get("/users/{uid}/edit")
def user_edit_page(uid: int, request: Request, user: User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    edit_user = db.get(User, uid)
    if edit_user is None:
        return RedirectResponse("/admin/users", status_code=303)
    return templates.TemplateResponse(request, "admin/users.html", _user_context(
        db, user, edit_user=edit_user, msg=request.query_params.get("msg", "")))


@router.post("/users/new")
async def user_create(request: Request, user: User = Depends(require_admin),
                      db: Session = Depends(get_db)):
    from ..models import User as U
    form = await request.form()
    email = (form.get("email") or "").strip().lower()
    if not email or not form.get("password"):
        return RedirectResponse("/admin/users?msg=Email и пароль обязательны", status_code=303)
    exists = db.execute(select(U).where(U.email == email)).scalar_one_or_none()
    if exists:
        return RedirectResponse("/admin/users?msg=Пользователь с таким email уже есть", status_code=303)
    role = form.get("role") or "Пользователь"
    new_user = U(email=email, full_name=(form.get("full_name") or "").strip(),
                 password_hash=hash_password(form.get("password")),
                 role=role if role in ROLES else "Пользователь",
                 is_active=(form.get("is_active") == "on"),
                 block_access=default_access_for_role(role))
    db.add(new_user)
    db.flush()
    _apply_access_overrides(new_user, form)
    from ..services.recalc import log_action
    log_action(db, user.email, "user", new_user.id, "создание", email)
    db.commit()
    return RedirectResponse("/admin/users?msg=Пользователь создан", status_code=303)


@router.post("/users/{uid}/edit")
async def user_edit(uid: int, request: Request, user: User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    target = db.get(User, uid)
    if target is None:
        return RedirectResponse("/admin/users", status_code=303)
    form = await request.form()
    target.full_name = (form.get("full_name") or "").strip()
    role = form.get("role") or target.role
    if role in ROLES:
        target.role = role
    target.is_active = form.get("is_active") == "on"
    if form.get("password"):
        target.password_hash = hash_password(form.get("password"))
    _apply_access_overrides(target, form)
    from ..services.recalc import log_action
    log_action(db, user.email, "user", uid, "изменение", target.email)
    db.commit()
    return RedirectResponse("/admin/users?msg=Пользователь сохранён", status_code=303)


def _apply_access_overrides(user: User, form) -> None:
    """Флажки «прав-по-роли» + явные уровни по блокам (ТЗ 2.1.2 «Назначение прав»)."""
    if form.get("reset_access") == "on":
        user.block_access = default_access_for_role(user.role)
        return
    access = normalize_access(user.block_access)
    for block in BLOCKS:
        level = form.get(f"access_{block}")
        if level in (EDIT, READ, NONE):
            access[block] = level
    user.block_access = access


@router.post("/users/{uid}/delete")
async def user_delete(uid: int, request: Request, user: User = Depends(require_admin),
                      db: Session = Depends(get_db)):
    if uid == user.id:
        return RedirectResponse("/admin/users?msg=Нельзя удалить себя", status_code=303)
    target = db.get(User, uid)
    if target is None:
        return RedirectResponse("/admin/users", status_code=303)
    from ..services.recalc import log_action
    log_action(db, user.email, "user", uid, "удаление", target.email)
    db.delete(target)
    db.commit()
    return RedirectResponse("/admin/users?msg=Пользователь удалён", status_code=303)


# ---------- Проекты и объекты ----------

@router.get("/projects")
def projects_page(request: Request, user: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    projects = db.execute(select(Project).order_by(Project.code)).scalars().all()
    return templates.TemplateResponse(request, "admin/projects.html", {
        "user": user, "projects": projects, "msg": request.query_params.get("msg", ""),
        "edit_project": None})


@router.post("/projects/new")
async def project_create(request: Request, user: User = Depends(require_admin),
                         db: Session = Depends(get_db)):
    form = await request.form()
    code = (form.get("code") or "").strip()
    name = (form.get("name") or "").strip()
    if not code or not name:
        return RedirectResponse("/admin/projects?msg=Код и название обязательны", status_code=303)
    if db.execute(select(Project).where(Project.code == code)).scalar_one_or_none():
        return RedirectResponse("/admin/projects?msg=Проект с таким кодом уже есть", status_code=303)
    project = Project(code=code, name=name, status="Действует")
    db.add(project)
    db.flush()
    from ..services.recalc import log_action
    log_action(db, user.email, "project", project.id, "создание", f"{code} {name}")
    db.commit()
    return RedirectResponse("/admin/projects?msg=Проект создан", status_code=303)


@router.post("/projects/{pid}/objects")
async def object_create(pid: int, request: Request, user: User = Depends(require_admin),
                        db: Session = Depends(get_db)):
    form = await request.form()
    name = (form.get("name") or "").strip()
    if name and db.get(Project, pid):
        obj = ProjectObject(project_id=pid, name=name,
                            address=(form.get("address") or "").strip())
        db.add(obj)
        db.flush()
        from ..services.recalc import log_action
        log_action(db, user.email, "object", obj.id, "создание", name[:80])
        db.commit()
    return RedirectResponse("/admin/projects", status_code=303)


@router.post("/objects/{oid}/delete")
async def object_delete(oid: int, request: Request, user: User = Depends(require_admin),
                        db: Session = Depends(get_db)):
    obj = db.get(ProjectObject, oid)
    if obj:
        from ..services.recalc import log_action
        log_action(db, user.email, "object", oid, "удаление", obj.name[:80])
        db.delete(obj)
        db.commit()
    return RedirectResponse("/admin/projects", status_code=303)


@router.post("/projects/{pid}/status")
async def project_status(pid: int, request: Request, user: User = Depends(require_admin),
                         db: Session = Depends(get_db)):
    project = db.get(Project, pid)
    if project:
        new_status = (await request.form()).get("status") or ""
        if new_status in ("Действует", "Закрыт"):
            project.status = new_status
            from ..services.recalc import log_action
            log_action(db, user.email, "project", pid, "статус", new_status)
            db.commit()
    return RedirectResponse("/admin/projects", status_code=303)


# ---------- Журнал изменений ----------

@router.get("/changelog")
def changelog_page(request: Request, user: User = Depends(require_admin),
                   db: Session = Depends(get_db), page: int = 0):
    total = db.execute(select(func.count(ChangeLog.id))).scalar()
    items = db.execute(select(ChangeLog).order_by(ChangeLog.at.desc())
                       .offset(page * PAGE_SIZE).limit(PAGE_SIZE)).scalars().all()
    return templates.TemplateResponse(request, "admin/changelog.html", {
        "user": user, "items": items, "page": page,
        "pages": (total + PAGE_SIZE - 1) // PAGE_SIZE, "total": total})
