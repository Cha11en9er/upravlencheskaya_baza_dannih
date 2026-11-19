"""Блок «Договоры и Оплаты» — вкладка Договоры ГП/СП + ДС (ТЗ 3.2)."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_admin, require_block
from ..models import Contract, ContractAmendment, Contractor, Payment, Project, ProjectObject, User
from ..parsing import parse_bool, parse_date, parse_id, parse_int
from ..services import rd_sections as rds
from ..services.export import build_xlsx, fmt_date
from ..services.recalc import apply_signed_amendment, log_action, recalc_contract
from ..templating import templates

router = APIRouter(prefix="/contracts")
PAGE_SIZE = 50


def _context(db: Session, user: User, **extra) -> dict:
    ctx = {
        "user": user,
        "projects": db.execute(select(Project).order_by(Project.code)).scalars().all(),
        "objects": db.execute(select(ProjectObject)).scalars().all(),
        "contractors": db.execute(select(Contractor).order_by(Contractor.name)).scalars().all(),
        "gp_contracts": db.execute(select(Contract).where(Contract.contract_type == "ГП")
                                   .order_by(Contract.number)).scalars().all(),
        "rd_sections": rds.RD_SECTIONS,
        "subjects": rds.SUBJECTS,
        "contract_types": rds.CONTRACT_TYPES,
        "statuses": rds.CONTRACT_STATUSES,
        "amendment_statuses": rds.AMENDMENT_STATUSES,
    }
    ctx.update(extra)
    return ctx


def _filtered(db: Session, project_id: int | None, status: str, ctype: str, q: str):
    stmt = select(Contract)
    if project_id:
        stmt = stmt.where(Contract.project_id == project_id)
    if status:
        stmt = stmt.where(Contract.status == status)
    if ctype:
        stmt = stmt.where(Contract.contract_type == ctype)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Contract.number.like(like) | Contract.note.like(like))
    return stmt


@router.get("")
def list_page(request: Request, user: User = Depends(require_block("contracts")),
              db: Session = Depends(get_db), page: int = 0,
              project_id: int = 0, status: str = "", ctype: str = "", q: str = ""):
    stmt = _filtered(db, project_id or None, status, ctype, q)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    items = db.execute(stmt.order_by(Contract.id.desc())
                       .offset(page * PAGE_SIZE).limit(PAGE_SIZE)).scalars().all()
    return templates.TemplateResponse(request, "contracts/list.html", _context(
        db, user, items=items, total=total, page=page, pages=(total + PAGE_SIZE - 1) // PAGE_SIZE,
        f_project_id=project_id, f_status=status, f_ctype=ctype, f_q=q,
        msg=request.query_params.get("msg", "")))


@router.get("/export.xlsx")
def export_xlsx(user: User = Depends(require_block("contracts")),
                db: Session = Depends(get_db),
                project_id: int = 0, status: str = "", ctype: str = "", q: str = ""):
    stmt = _filtered(db, project_id or None, status, ctype, q)
    items = db.execute(stmt.order_by(Contract.id.desc())).scalars().all()
    headers = ["ID", "Тип", "ID ГП", "№ договора", "Дата", "Проект", "Контрагент", "Предмет",
               "Раздел РД", "Сумма", "Аванс %", "Сумма аванса", "Дата начала", "Дата оконч.",
               "Статус", "Оплачено", "Остаток", "Просрочка (дней)", "Пени", "Риск", "Примечание"]
    rows = [[c.id, c.contract_type, c.parent_id or "", c.number, fmt_date(c.date),
             c.project_id or "", c.contractor.name if c.contractor else "",
             c.subject, c.rd_section, c.amount, c.advance_pct, c.advance_sum,
             fmt_date(c.date_start), fmt_date(c.date_end), c.status, c.paid, c.rest,
             c.overdue_days, c.penalty, c.risk, c.note] for c in items]
    buf = build_xlsx("Договоры", headers, rows,
                     [8, 8, 8, 16, 12, 18, 30, 10, 12, 14, 9, 14, 12, 12, 22, 14, 14, 12, 12, 8, 30])
    filename = f"contracts_{dt.date.today():%Y-%m-%d}.xlsx"
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"})


def _form_values(form) -> dict:
    return {
        "contract_type": form.get("contract_type") or "ГП",
        "parent_id": parse_id(form.get("parent_id")),
        "customer_id": parse_id(form.get("customer_id")),
        "gencontractor_id": parse_id(form.get("gencontractor_id")),
        "subcontractor_id": parse_id(form.get("subcontractor_id")),
        "contractor_id": parse_id(form.get("contractor_id")),
        "number": (form.get("number") or "").strip(),
        "date": parse_date(form.get("date")),
        "project_id": parse_id(form.get("project_id")),
        "object_id": parse_id(form.get("object_id")),
        "subject": form.get("subject") or "СМР",
        "rd_section": form.get("rd_section") or "",
        "amount": parse_int(form.get("amount")),
        "advance_pct": parse_int(form.get("advance_pct")),
        "date_start": parse_date(form.get("date_start")),
        "date_end": parse_date(form.get("date_end")),
        "status": form.get("status") or "Проект",
        "has_template": parse_bool(form.get("has_template")),
        "has_ird": parse_bool(form.get("has_ird")),
        "has_tz": parse_bool(form.get("has_tz")),
        "has_gf": parse_bool(form.get("has_gf")),
        "has_gpr": parse_bool(form.get("has_gpr")),
        "has_estimate": parse_bool(form.get("has_estimate")),
        "has_rd_vpr": parse_bool(form.get("has_rd_vpr")),
        "note": (form.get("note") or "").strip(),
        "link": (form.get("link") or "").strip(),
    }


@router.get("/new")
def new_page(request: Request, user: User = Depends(require_block("contracts", need_edit=True)),
             db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "contracts/form.html",
                                      _context(db, user, contract=None))


@router.post("/new")
async def create(request: Request, user: User = Depends(require_block("contracts", need_edit=True)),
                 db: Session = Depends(get_db)):
    contract = Contract(**_form_values(await request.form()))
    db.add(contract)
    db.flush()
    recalc_contract(db, contract)
    log_action(db, user.email, "contract", contract.id, "создание",
               f"№{contract.number} сумма={contract.amount}")
    db.commit()
    return RedirectResponse("/contracts?msg=Договор создан", status_code=303)


@router.get("/{cid}/edit")
def edit_page(cid: int, request: Request,
              user: User = Depends(require_block("contracts", need_edit=True)),
              db: Session = Depends(get_db)):
    contract = db.get(Contract, cid)
    if contract is None:
        return RedirectResponse("/contracts", status_code=303)
    return templates.TemplateResponse(request, "contracts/form.html",
                                      _context(db, user, contract=contract))


@router.post("/{cid}/edit")
async def edit(cid: int, request: Request,
               user: User = Depends(require_block("contracts", need_edit=True)),
               db: Session = Depends(get_db)):
    contract = db.get(Contract, cid)
    if contract is None:
        return RedirectResponse("/contracts", status_code=303)
    for key, value in _form_values(await request.form()).items():
        setattr(contract, key, value)
    recalc_contract(db, contract)
    log_action(db, user.email, "contract", contract.id, "изменение", f"№{contract.number}")
    db.commit()
    return RedirectResponse("/contracts?msg=Договор сохранён", status_code=303)


@router.post("/{cid}/status")
async def set_status(cid: int, request: Request,
                     user: User = Depends(require_block("contracts", need_edit=True)),
                     db: Session = Depends(get_db)):
    """Аннулирование / восстановление / архив (ТЗ 3.2.3.5)."""
    contract = db.get(Contract, cid)
    if contract is None:
        return RedirectResponse("/contracts", status_code=303)
    form = await request.form()
    new_status = form.get("status") or ""
    if new_status in rds.CONTRACT_STATUSES:
        contract.status = new_status
        recalc_contract(db, contract)
        log_action(db, user.email, "contract", contract.id, "статус",
                   f"№{contract.number}: {new_status}")
        db.commit()
    return RedirectResponse("/contracts?msg=Статус обновлён", status_code=303)


@router.post("/{cid}/delete")
async def delete(cid: int, request: Request, user: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    """ТЗ 3.2.3.5: физическое удаление — только Администратор и только пустые строки."""
    contract = db.get(Contract, cid)
    if contract is None:
        return RedirectResponse("/contracts", status_code=303)
    has_children = (contract.payments or contract.amendments
                    or db.execute(select(func.count(Contract.id))
                                  .where(Contract.parent_id == cid)).scalar())
    if has_children:
        return RedirectResponse("/contracts?msg=Заполненный договор удалить нельзя — аннулируйте",
                                status_code=303)
    log_action(db, user.email, "contract", contract.id, "удаление", f"№{contract.number}")
    db.delete(contract)
    db.commit()
    return RedirectResponse("/contracts?msg=Договор удалён", status_code=303)


@router.get("/{cid}")
def detail(cid: int, request: Request, user: User = Depends(require_block("contracts")),
           db: Session = Depends(get_db)):
    contract = db.get(Contract, cid)
    if contract is None:
        return RedirectResponse("/contracts", status_code=303)
    payments = db.execute(select(Payment).where(Payment.contract_id == cid)
                          .order_by(Payment.id)).scalars().all()
    return templates.TemplateResponse(request, "contracts/detail.html", _context(
        db, user, contract=contract, payments=payments,
        msg=request.query_params.get("msg", "")))


@router.post("/{cid}/amendments")
async def add_amendment(cid: int, request: Request,
                        user: User = Depends(require_block("contracts", need_edit=True)),
                        db: Session = Depends(get_db)):
    """Добавление ДС (ТЗ 3.2.3.4)."""
    contract = db.get(Contract, cid)
    if contract is None:
        return RedirectResponse("/contracts", status_code=303)
    form = await request.form()
    amendment = ContractAmendment(
        contract_id=cid,
        number=(form.get("number") or "").strip(),
        date=parse_date(form.get("date")),
        new_amount=parse_int(form.get("new_amount")),
        new_date_end=parse_date(form.get("new_date_end")),
        status=form.get("status") or "Проект",
        reason=(form.get("reason") or "").strip(),
    )
    db.add(amendment)
    db.flush()
    if amendment.status == "Подписан":
        apply_signed_amendment(db, contract, user.email)
    log_action(db, user.email, "amendment", amendment.id, "создание",
               f"ДС №{amendment.number} к договору {cid}")
    db.commit()
    return RedirectResponse(f"/contracts/{cid}?msg=ДС добавлено", status_code=303)


@router.post("/amendments/{aid}/status")
async def amendment_status(aid: int, request: Request,
                           user: User = Depends(require_block("contracts", need_edit=True)),
                           db: Session = Depends(get_db)):
    form = await request.form()
    amendment = db.get(ContractAmendment, aid)
    if amendment is None:
        return RedirectResponse("/contracts", status_code=303)
    new_status = form.get("status") or ""
    if new_status in rds.AMENDMENT_STATUSES:
        amendment.status = new_status
        contract = db.get(Contract, amendment.contract_id)
        if new_status == "Подписан":
            apply_signed_amendment(db, contract, user.email)
        recalc_contract(db, contract)
        log_action(db, user.email, "amendment", aid, "статус",
                   f"ДС №{amendment.number}: {new_status}")
        db.commit()
    return RedirectResponse(f"/contracts/{amendment.contract_id}?msg=Статус ДС обновлён", status_code=303)
