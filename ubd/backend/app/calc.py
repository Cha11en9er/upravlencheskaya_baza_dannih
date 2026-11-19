"""Чистые функции расчётов из ТЗ — без БД, покрыты тестами.

Риски (ТЗ п.4): green #C8E6C9 / yellow #FFF9C4 / red #FFCDD2.
Деньги — целые рубли (ТЗ п.9.2).
"""
from __future__ import annotations

from datetime import date

GREEN, YELLOW, RED = "green", "yellow", "red"


def advance_sum(amount: int, advance_pct: int) -> int:
    """Сумма аванса = Сумма * Аванс% (ТЗ 3.2.3.2 п.12)."""
    return int(round((amount or 0) * (advance_pct or 0) / 100))


def contract_overdue_days(today: date, date_end: date | None, status: str) -> int:
    """Просрочка только для статуса «Подписан» (ТЗ 3.2.3.3)."""
    if status != "Подписан" or date_end is None:
        return 0
    delta = (today - date_end).days
    return max(0, delta)


def penalty(amount: int, overdue_days: int) -> int:
    """Пени 0,1% в день (ТЗ 3.2.3.3): Сумма * 0.001 * Просрочка."""
    if overdue_days <= 0:
        return 0
    return int(round((amount or 0) * 0.001 * overdue_days))


def overdue_risk(overdue_days: int) -> str:
    """Зелёный — нет просрочки, жёлтый 1-5, красный >5 (ТЗ 3.2.3.3)."""
    if overdue_days <= 0:
        return GREEN
    if overdue_days <= 5:
        return YELLOW
    return RED


def payment_overdue_days(today: date, plan_date: date | None, status: str, fact_sum: int) -> int:
    """Просрочка платежа: статус Ожидание и дата плана прошла (ТЗ 3.3.3)."""
    if status != "Ожидание" or plan_date is None or fact_sum > 0:
        return 0
    return max(0, (today - plan_date).days)


def budget_calc(qty_plan: float, price_plan: int, qty_fact: float, price_fact: int) -> dict:
    """Расчёты бюджета (ТЗ 3.1.2): суммы, отклонение, %, риск."""
    sum_plan = int(round((qty_plan or 0) * (price_plan or 0)))
    sum_fact = int(round((qty_fact or 0) * (price_fact or 0)))
    deviation = sum_fact - sum_plan
    deviation_pct = round(deviation / sum_plan * 100, 2) if sum_plan else 0.0
    return {
        "sum_plan": sum_plan,
        "sum_fact": sum_fact,
        "deviation": deviation,
        "deviation_pct": deviation_pct,
        "risk": budget_risk(deviation_pct),
    }


def budget_risk(deviation_pct: float) -> str:
    """🟢 ≤5%, 🟡 5<x≤10%, 🔴 >10% (ТЗ 3.1.3)."""
    share = abs(deviation_pct)
    if share <= 5:
        return GREEN
    if share <= 10:
        return YELLOW
    return RED


def contract_date_from_tender(tender_end: date | None) -> date | None:
    """Дата подписания договора = дата конца тендера + 14 календарных дней (ТЗ 3.1.2)."""
    if tender_end is None:
        return None
    from datetime import timedelta
    return tender_end + timedelta(days=14)


def apply_amendment(contract_amount: int, contract_date_end, amendment) -> tuple[int, object]:
    """Подписанное ДС обновляет сумму и дату окончания договора (ТЗ 3.2.3.4)."""
    return amendment.new_amount, amendment.new_date_end
