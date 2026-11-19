"""Блок «Оплаты» (ТЗ 3.3 + вкладка 3.2.4)."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_admin, require_block
from ..models import Contract, Payment, Project, ProjectObject, User
from ..parsing import parse_date, parse_id, parse_int
from ..services import rd_sections as rds
from ..services.export import build_xlsx, fmt_date
from ..services.recalc import log_action, recalc_contract, recalc_payment
from ..templating import templates

router = APIRouter(prefix="/payments")
PAGE_SIZE = 50


def _context(db: Session, user: User, **extra) -> dict:
    ctx = {
        "user": user,
        "contracts": db.execute(select(Contract).order_by(Contract.number)).scalars().all(),
        "projects": db.execute(select(Project).order_by(Project.code)).scalars().all(),
        "objects": db.execute(select(ProjectObject)).scalars().all(),
        "kinds": rds.PAYMENT_KINDS,
        "stage_types": rds.PAYMENT_STAGE_TYPES,
        "statuses": rds.PAYMENT_STATUSES,
    }
    ctx.update(extra)
    return ctx


def _filtered(db: Session, contract_id: int | None, status: str, kind: str, q: str):
    stmt = select(Payment)
    if contract_id:
        stmt = stmt.where(Payment.contract_id == contract_id)
    if status:
        stmt = stmt.where(Payment.status == status)
    if kind:
        stmt = stmt.where(Payment.kind == kind)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Payment.note.like(like) | Payment.stage_label.like(like))
    return stmt


@router.get("")
def list_page(request: Request, user: User = Depends(require_block("payments")),
              db: Session = Depends(get_db), page: int = 0,
              contract_id: int = 0, status: str = "", kind: str = "", q: str = ""):
    stmt = _filtered(db, contract_id or None, status, kind, q)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    items = db.execute(stmt.order_by(Payment.id.desc())
                       .offset(page * PAGE_SIZE).limit(PAGE_SIZE)).scalars().all()
    # Суммы по текущему фильтру для сводки в футере (ТЗ 3.3.3)
    all_filtered = db.execute(stmt).scalars().all()
    in_sum = sum(int(p.fact_sum or 0) for p in all_filtered if p.kind == "Входящий")
    out_sum = sum(int(p.fact_sum or 0) for p in all_filtered if p.kind == "Исходящий")
    return templates.TemplateResponse(request, "payments/list.html", _context(
        db, user, items=items, total=total, page=page,
        pages=(total + PAGE_SIZE - 1) // PAGE_SIZE,
        f_contract_id=contract_id, f_status=status, f_kind=kind, f_q=q,
        in_sum=in_sum, out_sum=out_sum,
        msg=request.query_params.get("msg", "")))


@router.get("/export.xlsx")
def export_xlsx(user: User = Depends(require_block("payments")), db: Session = Depends(get_db),
                contract_id: int = 0, status: str = "", kind: str = "", q: str = ""):
    stmt = _filtered(db, contract_id or None, status, kind, q)
    items = db.execute(stmt.order_by(Payment.id.desc())).scalars().all()
    headers = ["ID", "Договор", "Тип", "Этап", "План. дата", "Факт. дата", "План. сумма",
               "Факт. сумма", "Статус", "Просрочка (дней)", "Риск", "Примечание"]
    rows = [[p.id, p.contract.number if p.contract else "", p.kind,
             f"{p.stage_type} {p.stage_label}".strip(), fmt_date(p.plan_date), fmt_date(p.fact_date),
             p.plan_sum, p.fact_sum, p.status, p.overdue_days, p.risk, p.note] for p in items]
    buf = build_xlsx("Оплаты", headers, rows,
                     [8, 18, 12, 18, 12, 12, 14, 14, 12, 14, 8, 30])
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=payments_{dt.date.today():%Y-%m-%d}.xlsx"})


def _form_values(form) -> dict:
    return {
        "contract_id": parse_id(form.get("contract_id")),
        "project_id": parse_id(form.get("project_id")),
        "object_id": parse_id(form.get("object_id")),
        "kind": form.get("kind") or "Исходящий",
        "stage_type": form.get("stage_type") or "Прочее",
        "stage_label": (form.get("stage_label") or "").strip(),
        "plan_date": parse_date(form.get("plan_date")),
        "fact_date": parse_date(form.get("fact_date")),
        "plan_sum": parse_int(form.get("plan_sum")),
        "fact_sum": parse_int(form.get("fact_sum")),
        "status": form.get("status") or "Ожидание",
        "note": (form.get("note") or "").strip(),
    }


@router.get("/new")
def new_page(request: Request, user: User = Depends(require_block("payments", need_edit=True)),
             db: Session = Depends(get_db), contract_id: int = 0):
    return templates.TemplateResponse(request, "payments/form.html",
                                      _context(db, user, payment=None, prefill_contract_id=contract_id))


@router.post("/new")
async def create(request: Request, user: User = Depends(require_block("payments", need_edit=True)),
                 db: Session = Depends(get_db)):
    payment = Payment(**_form_values(await request.form()))
    db.add(payment)
    db.flush()
    recalc_payment(db, payment)
    if payment.contract_id:
        recalc_contract(db, db.get(Contract, payment.contract_id))
    log_action(db, user.email, "payment", payment.id, "создание",
               f"{payment.kind} {payment.stage_type} {payment.plan_sum}")
    db.commit()
    return RedirectResponse("/payments?msg=Оплата создана", status_code=303)


@router.get("/{pid}/edit")
def edit_page(pid: int, request: Request,
              user: User = Depends(require_block("payments", need_edit=True)),
              db: Session = Depends(get_db)):
    payment = db.get(Payment, pid)
    if payment is None:
        return RedirectResponse("/payments", status_code=303)
    return templates.TemplateResponse(request, "payments/form.html",
                                      _context(db, user, payment=payment, prefill_contract_id=None))


@router.post("/{pid}/edit")
async def edit(pid: int, request: Request,
               user: User = Depends(require_block("payments", need_edit=True)),
               db: Session = Depends(get_db)):
    payment = db.get(Payment, pid)
    if payment is None:
        return RedirectResponse("/payments", status_code=303)
    for key, value in _form_values(await request.form()).items():
        setattr(payment, key, value)
    recalc_payment(db, payment)
    if payment.contract_id:
        recalc_contract(db, db.get(Contract, payment.contract_id))
    log_action(db, user.email, "payment", pid, "изменение", "")
    db.commit()
    return RedirectResponse("/payments?msg=Оплата сохранена", status_code=303)


@router.post("/{pid}/status")
async def set_status(pid: int, request: Request,
                     user: User = Depends(require_block("payments", need_edit=True)),
                     db: Session = Depends(get_db)):
    payment = db.get(Payment, pid)
    if payment is None:
        return RedirectResponse("/payments", status_code=303)
    new_status = (await request.form()).get("status") or ""
    if new_status in rds.PAYMENT_STATUSES:
        payment.status = new_status
        recalc_payment(db, payment)
        if payment.contract_id:
            recalc_contract(db, db.get(Contract, payment.contract_id))
        log_action(db, user.email, "payment", pid, "статус", new_status)
        db.commit()
    return RedirectResponse("/payments?msg=Статус обновлён", status_code=303)


@router.post("/{pid}/delete")
async def delete(pid: int, request: Request, user: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    payment = db.get(Payment, pid)
    if payment is None:
        return RedirectResponse("/payments", status_code=303)
    contract_id = payment.contract_id
    log_action(db, user.email, "payment", pid, "удаление", f"{payment.kind} {payment.fact_sum}")
    db.delete(payment)
    if contract_id:
        recalc_contract(db, db.get(Contract, contract_id))
    db.commit()
    return RedirectResponse("/payments?msg=Оплата удалена", status_code=303)
