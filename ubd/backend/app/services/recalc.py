"""Пересчёт сущностей + журнал изменений."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import calc
from ..models import BudgetItem, ChangeLog, Contract, Payment


def recalc_contract(db: Session, contract: Contract, today: date | None = None) -> Contract:
    """Пересчёт договора: аванс, оплачено, остаток, просрочка, пени, риск.

    Сумму оплат берём SQL-запросом: кэшированная коллекция contract.payments может
    быть устаревшей (например, загрузена до добавления оплат в той же сессии).
    """
    today = today or date.today()
    contract.advance_sum = calc.advance_sum(contract.amount, contract.advance_pct)
    contract.paid = db.execute(
        select(func.coalesce(func.sum(Payment.fact_sum), 0))
        .where(Payment.contract_id == contract.id)
    ).scalar()
    contract.rest = int(contract.amount or 0) - contract.paid
    contract.overdue_days = calc.contract_overdue_days(today, contract.date_end, contract.status)
    contract.penalty = calc.penalty(contract.amount, contract.overdue_days)
    contract.risk = calc.overdue_risk(contract.overdue_days)
    return contract


def recalc_payment(db: Session, payment: Payment, today: date | None = None) -> Payment:
    today = today or date.today()
    payment.overdue_days = calc.payment_overdue_days(today, payment.plan_date, payment.status, payment.fact_sum)
    payment.risk = calc.overdue_risk(payment.overdue_days)
    return payment


def recalc_budget_item(db: Session, item: BudgetItem) -> BudgetItem:
    res = calc.budget_calc(item.qty_plan, item.price_plan, item.qty_fact, item.price_fact)
    item.sum_plan = res["sum_plan"]
    item.sum_fact = res["sum_fact"]
    item.deviation = res["deviation"]
    item.deviation_pct = res["deviation_pct"]
    item.risk = res["risk"]
    item.contract_date = calc.contract_date_from_tender(item.tender_date_end)
    return item


def log_action(db: Session, user_email: str, entity: str, entity_id: int | None,
               action: str, details: str = "") -> None:
    db.add(ChangeLog(user_email=user_email, entity=entity, entity_id=entity_id, action=action,
                     details=details))


def apply_signed_amendment(db: Session, contract: Contract, user_email: str) -> str:
    """ТЗ 3.2.3.4: если ДС «Подписан», сумма и дата окончания договора обновляются
    по последнему подписанному ДС."""
    signed = [a for a in contract.amendments if a.status == "Подписан"]
    if not signed:
        return ""
    last = max(signed, key=lambda a: (a.date or date.min, a.id))
    contract.amount = last.new_amount
    contract.date_end = last.new_date_end
    recalc_contract(db, contract)
    log_action(db, user_email, "contract", contract.id, "амендмент",
               f"ДС №{last.number or last.id}: сумма={last.new_amount}, срок={last.new_date_end}")
    return f"ДС №{last.number or last.id} применено"
