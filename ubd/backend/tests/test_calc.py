"""Чистые калькуляции из ТЗ (п.3.1.3, 3.2.3.3, 3.3.3)."""
from datetime import date

from app import calc


def test_advance_sum():
    assert calc.advance_sum(25_000_000, 20) == 5_000_000
    assert calc.advance_sum(0, 20) == 0
    assert calc.advance_sum(123, 0) == 0


def test_contract_overdue_only_for_signed():
    today = date(2026, 11, 19)
    end = date(2026, 11, 1)
    assert calc.contract_overdue_days(today, end, "Подписан") == 18
    assert calc.contract_overdue_days(today, end, "Проект") == 0
    assert calc.contract_overdue_days(today, end, "Аннулирован") == 0
    assert calc.contract_overdue_days(today, date(2026, 12, 1), "Подписан") == 0
    assert calc.contract_overdue_days(today, None, "Подписан") == 0


def test_penalty_010_percent_per_day():
    # ТЗ: Пени = Сумма * 0.001 * Просрочка
    assert calc.penalty(4_500_000, 188) == 846_000
    assert calc.penalty(10_000, 5) == 50
    assert calc.penalty(10_000, 0) == 0


def test_overdue_risk_thresholds():
    assert calc.overdue_risk(0) == "green"
    assert calc.overdue_risk(1) == "yellow"
    assert calc.overdue_risk(5) == "yellow"
    assert calc.overdue_risk(6) == "red"


def test_budget_calc_and_risk():
    res = calc.budget_calc(5200, 8500, 2100, 8450)
    assert res["sum_plan"] == 44_200_000
    assert res["sum_fact"] == 17_745_000
    assert res["risk"] == "red"  # факт меньше плана на ~60% — по |отклонению|
    assert calc.budget_calc(1, 1_000_000, 1, 1_050_000)["risk"] == "green"   # ровно 5%
    assert calc.budget_calc(1, 1_000_000, 1, 1_099_999)["risk"] == "yellow"  # <10%
    assert calc.budget_calc(1, 1_000_000, 1, 1_100_000)["risk"] == "yellow"  # ровно 10% — по ТЗ ещё жёлтый
    assert calc.budget_calc(1, 1_000_000, 1, 1_100_060)["risk"] == "red"     # 10.01% > 10% после округления
    assert calc.budget_calc(0, 0, 0, 0)["risk"] == "green"  # план 0 — не делим на ноль


def test_payment_overdue_only_waiting_without_fact():
    today = date(2026, 11, 19)
    plan = date(2026, 11, 1)
    assert calc.payment_overdue_days(today, plan, "Ожидание", 0) == 18
    assert calc.payment_overdue_days(today, plan, "Оплачено", 1_000) == 0
    assert calc.payment_overdue_days(today, plan, "Ожидание", 500) == 0  # факт есть — не просрочено


def test_contract_date_from_tender_plus_14():
    assert calc.contract_date_from_tender(date(2025, 12, 20)) == date(2026, 1, 3)
    assert calc.contract_date_from_tender(None) is None


def test_apply_amendment():
    class A:
        new_amount = 27_500_000
        new_date_end = date(2026, 7, 1)
    amount, end = calc.apply_amendment(25_000_000, date(2026, 6, 1), A())
    assert amount == 27_500_000
    assert end == date(2026, 7, 1)
