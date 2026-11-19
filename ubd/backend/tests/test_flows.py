"""Сценарные тесты: договоры, ДС, оплаты, бюджет, контрагенты (через TestClient)."""
from datetime import date, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import BudgetItem, Contract, ContractAmendment, Contractor, Payment


def test_create_contract_and_calcs(admin_client):
    resp = admin_client.post("/contracts/new", data={
        "contract_type": "ГП",
        "number": "ГП-TEST-001",
        "date": "2026-01-10",
        "amount": "10_000_000",
        "advance_pct": "15",
        "date_start": "2026-02-01",
        "date_end": (date.today() - timedelta(days=10)).isoformat(),
        "status": "Подписан",
        "subject": "СМР",
    }, follow_redirects=False)
    assert resp.status_code == 303

    db = SessionLocal()
    try:
        c = db.execute(select(Contract).where(Contract.number == "ГП-TEST-001")).scalar_one()
        assert c.amount == 10_000_000
        assert c.advance_sum == 1_500_000
        assert c.overdue_days == 10
        assert c.penalty == 100_000      # 10 000 000 * 0.001 * 10
        assert c.risk == "red"
    finally:
        db.close()


def test_payment_updates_contract(admin_client):
    db = SessionLocal()
    cid = db.execute(select(Contract).where(Contract.number == "ГП-TEST-001")).scalar_one().id
    db.close()

    resp = admin_client.post("/payments/new", data={
        "contract_id": str(cid),
        "kind": "Входящий",
        "stage_type": "Аванс",
        "plan_sum": "1500000",
        "fact_sum": "1500000",
        "status": "Оплачено",
    }, follow_redirects=False)
    assert resp.status_code == 303

    db = SessionLocal()
    try:
        c = db.get(Contract, cid)
        assert c.paid == 1_500_000
        assert c.rest == 8_500_000
        p = db.execute(select(Payment).where(Payment.contract_id == cid)).scalar_one()
        assert p.overdue_days == 0
    finally:
        db.close()


def test_signed_amendment_applies_to_contract(admin_client):
    db = SessionLocal()
    cid = db.execute(select(Contract).where(Contract.number == "ГП-TEST-001")).scalar_one().id
    db.close()

    new_end = (date.today() + timedelta(days=60)).isoformat()
    resp = admin_client.post(f"/contracts/{cid}/amendments", data={
        "number": "ДС-TEST-1",
        "date": "2026-11-01",
        "new_amount": "12000000",
        "new_date_end": new_end,
        "status": "Подписан",
        "reason": "Доп. работы",
    }, follow_redirects=False)
    assert resp.status_code == 303

    db = SessionLocal()
    try:
        c = db.get(Contract, cid)
        assert c.amount == 12_000_000          # ТЗ 3.2.3.4: ДС обновляет договор
        assert c.date_end.isoformat() == new_end
        assert c.overdue_days == 0             # срок продлён — просрочки больше нет
        assert c.penalty == 0
        a = db.execute(select(ContractAmendment)
                       .where(ContractAmendment.number == "ДС-TEST-1")).scalar_one()
        assert a.status == "Подписан"
    finally:
        db.close()


def test_budget_item_recalc(admin_client):
    resp = admin_client.post("/budget/new", data={
        "work_name": "Тестовые работы",
        "article": "СМР",
        "unit": "м3",
        "qty_plan": "100",
        "price_plan": "50000",
        "qty_fact": "100",
        "price_fact": "56000",
        "tender_date_end": "2025-12-20",
    }, follow_redirects=False)
    assert resp.status_code == 303

    db = SessionLocal()
    try:
        b = db.execute(select(BudgetItem).where(BudgetItem.work_name == "Тестовые работы")).scalar_one()
        assert b.sum_plan == 5_000_000
        assert b.sum_fact == 5_600_000
        assert b.deviation == 600_000
        assert b.deviation_pct == 12.0
        assert b.risk == "red"                  # отклонение > 10%
        assert b.contract_date == date(2026, 1, 3)  # тендер конец + 14 к.д.
    finally:
        db.close()


def test_contractor_form_create_and_import_mapping(admin_client):
    resp = admin_client.post("/contractors/new", data={
        "name": "ООО «Тестовый подрядчик»",
        "inn": "7700123456",
        "contract_type": "СП",
        "phone": "8 (495) 000-00-00",
        "email": "test@example.ru",
    }, follow_redirects=False)
    assert resp.status_code == 303
    db = SessionLocal()
    try:
        c = db.execute(select(Contractor).where(Contractor.inn == "7700123456")).scalar_one()
        assert c.name == "ООО «Тестовый подрядчик»"
        assert c.contract_type == "СП"
    finally:
        db.close()

    from app.services.contractor_import import map_row
    mapped = map_row({"ИНН": "7700999", "Название": "ООО «Импорт»", "Категория": "Генподрядчик",
                      "Телефон": "8 (800) 1\n8 (800) 2", "Почта": "a@b.ru\nc@d.ru",
                      "Оборот 2025, ₽": "1 234 567 ₽", "Статус": "действующая организация"})
    assert mapped["inn"] == "7700999"
    assert mapped["contract_type"] == "ГП"
    assert mapped["phone"] == "8 (800) 1"
    assert mapped["revenue_2025"] == 1_234_567


def test_annul_and_admin_delete_rules(admin_client):
    # пустой договор СП без детей: админ может удалить
    resp = admin_client.post("/contracts/new", data={
        "contract_type": "СП", "number": "СП-EMPTY", "amount": "0", "status": "Проект",
    }, follow_redirects=False)
    assert resp.status_code == 303
    db = SessionLocal()
    try:
        cid = db.execute(select(Contract).where(Contract.number == "СП-EMPTY")).scalar_one().id
    finally:
        db.close()
    resp = admin_client.post(f"/contracts/{cid}/delete", follow_redirects=False)
    assert resp.status_code == 303
    db = SessionLocal()
    try:
        assert db.execute(select(Contract).where(Contract.number == "СП-EMPTY")).scalar_one_or_none() is None
    finally:
        db.close()

    # договор с оплатой удалить нельзя → сначала аннулирование
    db = SessionLocal()
    try:
        cid = db.execute(select(Contract).where(Contract.number == "ГП-TEST-001")).scalar_one().id
    finally:
        db.close()
    resp = admin_client.post(f"/contracts/{cid}/delete", follow_redirects=False)
    assert resp.status_code == 303
    db = SessionLocal()
    try:
        assert db.get(Contract, cid) is not None
        resp2 = admin_client.post(f"/contracts/{cid}/status",
                                  data={"status": "Аннулирован"}, follow_redirects=False)
        assert resp2.status_code == 303
        assert db.get(Contract, cid).status == "Аннулирован"
    finally:
        db.close()


def test_changelog_recorded(admin_client):
    db = SessionLocal()
    try:
        from sqlalchemy import func
        from app.models import ChangeLog
        count = db.execute(select(func.count(ChangeLog.id))).scalar()
        assert count >= 5  # создания договоров/оплат/ДС/бюджета из тестов выше
    finally:
        db.close()
