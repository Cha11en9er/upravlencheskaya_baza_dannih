"""Главная страница (ТЗ 2.1.3): приветствие, карточки-виджеты, плитка блоков."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import block_level, page_user
from ..models import BudgetItem, Contract, Payment, Project, User
from ..permissions import BLOCKS, EDIT, READ
from ..templating import templates

router = APIRouter()


@router.get("/")
def dashboard(request: Request, user: User = Depends(page_user), db: Session = Depends(get_db)):
    contracts = select(Contract).where(Contract.status != "Аннулирован")
    contracts_sum = db.execute(select(func.coalesce(func.sum(Contract.amount), 0))
                               .where(Contract.status != "Аннулирован")).scalar()
    paid_sum = db.execute(select(func.coalesce(func.sum(Contract.paid), 0))
                          .where(Contract.status != "Аннулирован")).scalar()
    projects_count = db.execute(select(func.count(Project.id))).scalar()
    red_contracts = db.execute(select(func.count(Contract.id))
                               .where(Contract.risk == "red", Contract.status != "Аннулирован")).scalar()
    red_payments = db.execute(select(func.count(Payment.id)).where(Payment.risk == "red")).scalar()
    red_budget = db.execute(select(func.count(BudgetItem.id))
                            .where(BudgetItem.risk == "red", BudgetItem.status == "Действует")).scalar()

    tiles = []
    for key, (label, implemented) in BLOCKS.items():
        level = block_level(user, key)
        tiles.append({"key": key, "label": label, "implemented": implemented,
                      "level": level, "icon": "✏️" if level == EDIT else ("📖" if level == READ else "🔒")})

    return templates.TemplateResponse(request, "dashboard.html", {
        "user": user,
        "kpi": {
            "projects": projects_count,
            "contracts_sum": contracts_sum,
            "paid_sum": paid_sum,
            "risks": (red_contracts or 0) + (red_payments or 0) + (red_budget or 0),
        },
        "tiles": tiles,
    })
