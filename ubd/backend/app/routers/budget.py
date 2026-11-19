"""Блок «Бюджет и ГрП» (ТЗ 3.1)."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_admin, require_block
from ..models import BudgetItem, Project, ProjectObject, User
from ..parsing import parse_date, parse_float, parse_id, parse_int
from ..services import rd_sections as rds
from ..services.export import build_xlsx, fmt_date
from ..services.recalc import log_action, recalc_budget_item
from ..templating import templates

router = APIRouter(prefix="/budget")
PAGE_SIZE = 50


def _context(db: Session, user: User, **extra) -> dict:
    ctx = {
        "user": user,
        "projects": db.execute(select(Project).order_by(Project.code)).scalars().all(),
        "objects": db.execute(select(ProjectObject)).scalars().all(),
        "rd_sections": rds.RD_SECTIONS,
        "articles": rds.ARTICLES,
        "units": rds.UNITS,
    }
    ctx.update(extra)
    return ctx


def _filtered(db: Session, project_id: int | None, object_id: int | None,
              article: str, rd: str, show_annulled: bool):
    stmt = select(BudgetItem)
    if project_id:
        stmt = stmt.where(BudgetItem.project_id == project_id)
    if object_id:
        stmt = stmt.where(BudgetItem.object_id == object_id)
    if article:
        stmt = stmt.where(BudgetItem.article == article)
    if rd:
        stmt = stmt.where(BudgetItem.rd_section == rd)
    if not show_annulled:
        stmt = stmt.where(BudgetItem.status != "Аннулирован")
    return stmt


@router.get("")
def list_page(request: Request, user: User = Depends(require_block("budget")),
              db: Session = Depends(get_db), page: int = 0,
              project_id: int = 0, object_id: int = 0, article: str = "", rd: str = "",
              annulled: int = 0):
    stmt = _filtered(db, project_id or None, object_id or None, article, rd, bool(annulled))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    items = db.execute(stmt.order_by(BudgetItem.id.desc())
                       .offset(page * PAGE_SIZE).limit(PAGE_SIZE)).scalars().all()
    return templates.TemplateResponse(request, "budget/list.html", _context(
        db, user, items=items, total=total, page=page,
        pages=(total + PAGE_SIZE - 1) // PAGE_SIZE,
        f_project_id=project_id, f_object_id=object_id, f_article=article, f_rd=rd,
        f_annulled=annulled, msg=request.query_params.get("msg", "")))


@router.get("/export.xlsx")
def export_xlsx(user: User = Depends(require_block("budget")), db: Session = Depends(get_db),
                project_id: int = 0, object_id: int = 0, article: str = "", rd: str = "",
                annulled: int = 0):
    stmt = _filtered(db, project_id or None, object_id or None, article, rd, bool(annulled))
    items = db.execute(stmt.order_by(BudgetItem.id.desc())).scalars().all()
    headers = ["ID", "Проект", "Объект", "Раздел РД", "Статья", "Наименование работ", "Ед.",
               "Кол-во план", "Цена план", "Сумма план", "Кол-во факт", "Цена факт",
               "Сумма факт", "Отклонение", "%", "Риск", "Статус",
               "Тендер нач.", "Тендер кон.", "Дата договора", "Работы нач.", "Работы кон.",
               "Дата ввода", "Примечание"]
    rows = [[b.id, b.project_id or "", b.object_id or "", b.rd_section, b.article, b.work_name,
             b.unit, b.qty_plan, b.price_plan, b.sum_plan, b.qty_fact, b.price_fact,
             b.sum_fact, b.deviation, b.deviation_pct, b.risk, b.status,
             fmt_date(b.tender_date_start), fmt_date(b.tender_date_end), fmt_date(b.contract_date),
             fmt_date(b.work_date_start), fmt_date(b.work_date_end),
             fmt_date(b.commissioning_date), b.note] for b in items]
    buf = build_xlsx("Бюджет", headers, rows,
                     [8, 14, 16, 12, 10, 32, 8, 12, 12, 14, 12, 12, 14, 14, 8, 8, 12, 12, 12, 12, 12, 12, 12, 24])
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=budget_{dt.date.today():%Y-%m-%d}.xlsx"})


def _form_values(form) -> dict:
    return {
        "project_id": parse_id(form.get("project_id")),
        "object_id": parse_id(form.get("object_id")),
        "rd_section": form.get("rd_section") or "",
        "article": form.get("article") or "СМР",
        "work_name": (form.get("work_name") or "").strip(),
        "unit": form.get("unit") or "шт",
        "qty_plan": parse_float(form.get("qty_plan")),
        "price_plan": parse_int(form.get("price_plan")),
        "qty_fact": parse_float(form.get("qty_fact")),
        "price_fact": parse_int(form.get("price_fact")),
        "note": (form.get("note") or "").strip(),
        "tender_date_start": parse_date(form.get("tender_date_start")),
        "tender_date_end": parse_date(form.get("tender_date_end")),
        "work_date_start": parse_date(form.get("work_date_start")),
        "work_date_end": parse_date(form.get("work_date_end")),
        "commissioning_date": parse_date(form.get("commissioning_date")),
    }


@router.get("/new")
def new_page(request: Request, user: User = Depends(require_block("budget", need_edit=True)),
             db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "budget/form.html",
                                      _context(db, user, item=None))


@router.post("/new")
async def create(request: Request, user: User = Depends(require_block("budget", need_edit=True)),
                 db: Session = Depends(get_db)):
    item = BudgetItem(**_form_values(await request.form()))
    db.add(item)
    db.flush()
    recalc_budget_item(db, item)
    log_action(db, user.email, "budget", item.id, "создание", f"{item.work_name[:60]}")
    db.commit()
    return RedirectResponse("/budget?msg=Строка бюджета создана", status_code=303)


@router.get("/{bid}/edit")
def edit_page(bid: int, request: Request,
              user: User = Depends(require_block("budget", need_edit=True)),
              db: Session = Depends(get_db)):
    item = db.get(BudgetItem, bid)
    if item is None:
        return RedirectResponse("/budget", status_code=303)
    return templates.TemplateResponse(request, "budget/form.html",
                                      _context(db, user, item=item))


@router.post("/{bid}/edit")
async def edit(bid: int, request: Request,
               user: User = Depends(require_block("budget", need_edit=True)),
               db: Session = Depends(get_db)):
    item = db.get(BudgetItem, bid)
    if item is None:
        return RedirectResponse("/budget", status_code=303)
    for key, value in _form_values(await request.form()).items():
        setattr(item, key, value)
    recalc_budget_item(db, item)
    log_action(db, user.email, "budget", bid, "изменение", f"{item.work_name[:60]}")
    db.commit()
    return RedirectResponse("/budget?msg=Строка бюджета сохранена", status_code=303)


@router.post("/{bid}/status")
async def set_status(bid: int, request: Request,
                     user: User = Depends(require_block("budget", need_edit=True)),
                     db: Session = Depends(get_db)):
    item = db.get(BudgetItem, bid)
    if item is None:
        return RedirectResponse("/budget", status_code=303)
    new_status = (await request.form()).get("status") or ""
    if new_status in ("Действует", "Аннулирован"):
        item.status = new_status
        log_action(db, user.email, "budget", bid, "статус", new_status)
        db.commit()
    return RedirectResponse("/budget?msg=Статус обновлён", status_code=303)


@router.post("/{bid}/delete")
async def delete(bid: int, request: Request, user: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    """ТЗ 3.1.3: удалять можно только пустые аннулированные строки."""
    item = db.get(BudgetItem, bid)
    if item is None:
        return RedirectResponse("/budget", status_code=303)
    has_content = item.work_name or item.qty_plan or item.qty_fact or item.price_plan
    if item.status != "Аннулирован" or has_content:
        return RedirectResponse("/budget?msg=Удалять можно только пустые аннулированные строки",
                                status_code=303)
    log_action(db, user.email, "budget", bid, "удаление", "")
    db.delete(item)
    db.commit()
    return RedirectResponse("/budget?msg=Строка удалена", status_code=303)
