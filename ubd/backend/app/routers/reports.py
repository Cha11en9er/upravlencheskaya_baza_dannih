"""Блок «Отчеты» (ТЗ 3.4): сводный по договорам, сводный по оплатам, реестр рисков."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_block
from ..models import Contract, Payment, Project, User
from ..services.export import build_xlsx, fmt_date
from ..templating import templates

router = APIRouter(prefix="/reports")


@router.get("")
def index(request: Request, user: User = Depends(require_block("reports")),
          db: Session = Depends(get_db),
          report: str = "contracts", project_id: int = 0, date_from: str = "", date_to: str = ""):
    from ..parsing import parse_date

    projects = db.execute(select(Project).order_by(Project.code)).scalars().all()
    ctx = {"user": user, "projects": projects, "report": report,
           "f_project_id": project_id, "f_from": date_from, "f_to": date_to}

    pid = project_id or None
    if report == "payments":
        stmt = select(Payment).order_by(Payment.id.desc())
        if pid:
            stmt = stmt.where(Payment.project_id == pid)
        items = db.execute(stmt.limit(2000)).scalars().all()
        ctx["items"] = items
        ctx["total_plan"] = sum(p.plan_sum or 0 for p in items)
        ctx["total_fact"] = sum(p.fact_sum or 0 for p in items)
    elif report == "risks":
        contracts = db.execute(select(Contract)
                               .where(Contract.risk == "red", Contract.status == "Подписан")
                               .order_by(Contract.penalty.desc())).scalars().all()
        payments = db.execute(select(Payment).where(Payment.risk == "red")
                              .order_by(Payment.overdue_days.desc())).scalars().all()
        ctx["contracts"] = contracts
        ctx["payments"] = payments
    else:
        report = "contracts"
        stmt = select(Contract).where(Contract.status != "Аннулирован").order_by(Contract.id.desc())
        if pid:
            stmt = stmt.where(Contract.project_id == pid)
        items = db.execute(stmt.limit(2000)).scalars().all()
        ctx["items"] = items
        ctx["sum_amount"] = sum(c.amount or 0 for c in items)
        ctx["sum_paid"] = sum(c.paid or 0 for c in items)
        ctx["sum_rest"] = sum(c.rest or 0 for c in items)
    ctx["msg"] = request.query_params.get("msg", "")
    return templates.TemplateResponse(request, "reports/index.html", ctx)


@router.get("/export.xlsx")
def export_xlsx(user: User = Depends(require_block("reports")), db: Session = Depends(get_db),
                report: str = "contracts", project_id: int = 0):
    pid = project_id or None
    if report == "risks":
        headers = ["Тип", "ID", "Документ", "Сумма", "Просрочка (дней)", "Пени"]
        rows = [["Договор", c.id, f"{c.contract_type} №{c.number}", c.amount,
                 c.overdue_days, c.penalty]
                for c in db.execute(select(Contract).where(Contract.risk == "red")).scalars()]
        rows += [["Оплата", p.id, p.stage_type, p.fact_sum, p.overdue_days, 0]
                 for p in db.execute(select(Payment).where(Payment.risk == "red")).scalars()]
        title = "Реестр рисков"
    elif report == "payments":
        stmt = select(Payment).order_by(Payment.id.desc())
        if pid:
            stmt = stmt.where(Payment.project_id == pid)
        headers = ["ID", "Договор", "Тип", "Этап", "План. дата", "Факт. дата", "План. сумма",
                   "Факт. сумма", "Статус", "Просрочка"]
        rows = [[p.id, p.contract.number if p.contract else "", p.kind,
                 f"{p.stage_type} {p.stage_label}".strip(), fmt_date(p.plan_date),
                 fmt_date(p.fact_date), p.plan_sum, p.fact_sum, p.status, p.overdue_days]
                for p in db.execute(stmt.limit(5000)).scalars()]
        title = "Сводный по оплатам"
    else:
        report = "contracts"
        stmt = select(Contract).where(Contract.status != "Аннулирован").order_by(Contract.id.desc())
        if pid:
            stmt = stmt.where(Contract.project_id == pid)
        headers = ["ID", "Тип", "№ договора", "Дата", "Проект", "Контрагент", "Предмет",
                   "Сумма", "Оплачено", "Остаток", "Просрочка", "Пени", "Риск", "Статус"]
        rows = [[c.id, c.contract_type, c.number, fmt_date(c.date), c.project_id or "",
                 c.contractor.name if c.contractor else "", c.subject, c.amount, c.paid,
                 c.rest, c.overdue_days, c.penalty, c.risk, c.status]
                for c in db.execute(stmt.limit(5000)).scalars()]
        title = "Сводный по договорам"
    buf = build_xlsx(title, headers, rows)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=report_{report}_{dt.date.today():%Y-%m-%d}.xlsx"})
