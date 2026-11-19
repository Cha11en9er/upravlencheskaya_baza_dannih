"""Справочник «Карточка контрагента» (ТЗ 3.2.6) + импорт из Excel Синапс."""
from __future__ import annotations

import datetime as dt
import io
import re

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_admin, require_block
from ..models import Contractor, User
from ..parsing import parse_int
from ..services import rd_sections as rds
from ..services.export import build_xlsx
from ..services.recalc import log_action
from ..templating import templates

router = APIRouter(prefix="/contractors")
PAGE_SIZE = 50
IMPORT_CAP = 200_000  # защитный предел строк за один импорт


def _context(db: Session, user: User, **extra) -> dict:
    ctx = {
        "user": user,
        "contractor_types": rds.CONTRACTOR_TYPES,
        "sb_statuses": rds.SB_STATUSES,
    }
    ctx.update(extra)
    return ctx


def _filtered(db: Session, q: str, ctype: str):
    stmt = select(Contractor)
    if q:
        like = f"%{q.strip()}%"
        digits = re.sub(r"\D", "", q)
        conds = [Contractor.name.like(like), Contractor.director.like(like),
                 Contractor.email.like(like)]
        if digits:
            conds.append(Contractor.inn.like(f"%{digits}%"))
        stmt = stmt.where(or_(*conds))
    if ctype:
        stmt = stmt.where(Contractor.contract_type == ctype)
    return stmt


@router.get("")
def list_page(request: Request, user: User = Depends(require_block("contracts")),
              db: Session = Depends(get_db), page: int = 0, q: str = "", ctype: str = ""):
    stmt = _filtered(db, q, ctype)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    items = db.execute(stmt.order_by(Contractor.name).offset(page * PAGE_SIZE)
                       .limit(PAGE_SIZE)).scalars().all()
    return templates.TemplateResponse(request, "contractors/list.html", _context(
        db, user, items=items, total=total, page=page,
        pages=(total + PAGE_SIZE - 1) // PAGE_SIZE,
        f_q=q, f_ctype=ctype, msg=request.query_params.get("msg", "")))


@router.get("/export.xlsx")
def export_xlsx(user: User = Depends(require_block("contracts")), db: Session = Depends(get_db),
                q: str = "", ctype: str = ""):
    stmt = _filtered(db, q, ctype)
    items = db.execute(stmt.order_by(Contractor.name)).scalars().all()
    headers = ["ID", "Тип", "Наименование", "ИНН", "КПП", "ОГРН", "Юр. адрес", "Город",
               "Ген. директор", "Телефон", "Email", "Статус СБ", "Оборот 2025", "Статус ЕГРЮЛ",
               "СРО", "Источник"]
    rows = [[c.id, c.contract_type, c.name, c.inn, c.kpp, c.ogrn, c.legal_address, c.city,
             c.director, c.phone, c.email, c.sb_status, c.revenue_2025 or "", c.egrul_status,
             c.sro_name, c.source] for c in items]
    buf = build_xlsx("Контрагенты", headers, rows,
                     [8, 12, 40, 14, 12, 14, 40, 16, 26, 22, 28, 14, 14, 14, 30, 10])
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=contractors_{dt.date.today():%Y-%m-%d}.xlsx"})


def _form_values(form) -> dict:
    return {
        "contract_type": form.get("contract_type") or "Прочие",
        "name": (form.get("name") or "").strip(),
        "inn": re.sub(r"\D", "", form.get("inn") or ""),
        "kpp": re.sub(r"\D", "", form.get("kpp") or ""),
        "ogrn": re.sub(r"\D", "", form.get("ogrn") or ""),
        "bik": re.sub(r"\D", "", form.get("bik") or ""),
        "checking_account": (form.get("checking_account") or "").strip(),
        "corr_account": (form.get("corr_account") or "").strip(),
        "legal_address": (form.get("legal_address") or "").strip(),
        "physical_address": (form.get("physical_address") or "").strip(),
        "director": (form.get("director") or "").strip(),
        "phone": (form.get("phone") or "").strip(),
        "email": (form.get("email") or "").strip(),
        "city": (form.get("city") or "").strip(),
        "sb_status": form.get("sb_status") or "",
        "work_type_rd": form.get("work_type_rd") or "",
    }


@router.get("/import")
def import_page(request: Request, user: User = Depends(require_block("contracts", need_edit=True))):
    return templates.TemplateResponse(request, "contractors/import.html",
                                      {"user": user, "msg": request.query_params.get("msg", ""),
                                       "err": request.query_params.get("err", "")})


@router.post("/import")
async def import_xlsx(request: Request, user: User = Depends(require_block("contracts", need_edit=True)),
                      db: Session = Depends(get_db), file: UploadFile = File(None)):
    from ..services.contractor_import import import_workbook

    if file is None or not file.filename:
        return RedirectResponse("/contractors/import?err=Файл не выбран", status_code=303)
    try:
        from openpyxl import load_workbook
        raw = await file.read()
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        return RedirectResponse(f"/contractors/import?err=Не удалось открыть файл: {exc}", status_code=303)

    created, updated, skipped = import_workbook(db, wb, cap_per_sheet=IMPORT_CAP)
    db.commit()
    log_action(db, user.email, "contractor", None, "импорт",
               f"{file.filename}: новых {created}, обновлено {updated}")
    db.commit()
    return RedirectResponse(f"/contractors?msg=Импорт завершён: новых {created}, обновлено {updated}",
                            status_code=303)


@router.get("/new")
def new_page(request: Request, user: User = Depends(require_block("contracts", need_edit=True)),
             db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "contractors/form.html",
                                      _context(db, user, contractor=None))


@router.post("/new")
async def create(request: Request, user: User = Depends(require_block("contracts", need_edit=True)),
                 db: Session = Depends(get_db)):
    values = _form_values(await request.form())
    if not values["name"]:
        return RedirectResponse("/contractors?err=Укажите наименование", status_code=303)
    contractor = Contractor(**values)
    db.add(contractor)
    db.flush()
    log_action(db, user.email, "contractor", contractor.id, "создание", contractor.name[:80])
    db.commit()
    return RedirectResponse("/contractors?msg=Контрагент создан", status_code=303)


@router.get("/{cid}/edit")
def edit_page(cid: int, request: Request,
              user: User = Depends(require_block("contracts", need_edit=True)),
              db: Session = Depends(get_db)):
    contractor = db.get(Contractor, cid)
    if contractor is None:
        return RedirectResponse("/contractors", status_code=303)
    return templates.TemplateResponse(request, "contractors/form.html",
                                      _context(db, user, contractor=contractor))


@router.post("/{cid}/edit")
async def edit(cid: int, request: Request,
               user: User = Depends(require_block("contracts", need_edit=True)),
               db: Session = Depends(get_db)):
    contractor = db.get(Contractor, cid)
    if contractor is None:
        return RedirectResponse("/contractors", status_code=303)
    for key, value in _form_values(await request.form()).items():
        setattr(contractor, key, value)
    log_action(db, user.email, "contractor", cid, "изменение", contractor.name[:80])
    db.commit()
    return RedirectResponse("/contractors?msg=Контрагент сохранён", status_code=303)


@router.post("/{cid}/delete")
async def delete(cid: int, request: Request, user: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    contractor = db.get(Contractor, cid)
    if contractor is None:
        return RedirectResponse("/contractors", status_code=303)
    log_action(db, user.email, "contractor", cid, "удаление", contractor.name[:80])
    db.delete(contractor)
    db.commit()
    return RedirectResponse("/contractors?msg=Контрагент удалён", status_code=303)
