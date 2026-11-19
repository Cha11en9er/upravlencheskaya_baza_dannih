"""Сид данных: админ, демо-данные, импорт топ-контрагентов из выгрузки Синапс.

Запуск:
    python -m app.seed            # сид админа + демо + импорт (если пусто)
    python -m app.seed --reset    # пересоздать демо (контрагенты/договоры не трогаем, если есть)
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import func, select

from .db import Base, SessionLocal, engine
from .models import (BudgetItem, ChangeLog, Contract, ContractAmendment, Contractor, Payment,
                     Project, ProjectObject, User)
from .permissions import default_access_for_role
from .security import hash_password
from .services.recalc import recalc_budget_item, recalc_contract, recalc_payment
from .config import settings

UBD_DIR = Path(__file__).resolve().parents[2]           # ubd/
REPO_ROOT = UBD_DIR.parent                               # Dmitiy_stroitelnaya_kompaniya/
EXPORT_XLSX = REPO_ROOT / "export" / "девелоперы_генподрядчики_синапс.xlsx"


def seed_admin(db) -> bool:
    if db.execute(select(func.count(User.id))).scalar():
        return False
    # Простой вход для МВП (временно; сменить до реального многопользовательского
    # использования — см. DECISIONS.md).
    db.add(User(email="админ", full_name="Администратор (простой вход)",
                password_hash=hash_password("1"),
                role="Администратор", is_active=True,
                block_access=default_access_for_role("Администратор")))
    db.add(User(email=settings.admin_email.lower(), full_name="Администратор",
                password_hash=hash_password(settings.admin_password),
                role="Администратор", is_active=True,
                block_access=default_access_for_role("Администратор")))
    db.add(User(email="rp@ubd.local", full_name="Иванов Пётр Сергеевич",
                password_hash=hash_password("user123"),
                role="Руководитель проекта", is_active=True,
                block_access=default_access_for_role("Руководитель проекта")))
    db.add(User(email="fin@ubd.local", full_name="Смирнова Анна Львовна",
                password_hash=hash_password("user123"),
                role="Финансист", is_active=True,
                block_access=default_access_for_role("Финансист")))
    db.commit()
    return True


def seed_demo(db) -> bool:
    if db.execute(select(func.count(Project.id))).scalar():
        return False

    p1 = Project(code="P-001", name="ЖК «Люкс»", status="Действует")
    p2 = Project(code="P-002", name="ЖК «Гранит»", status="Действует")
    db.add_all([p1, p2])
    db.flush()
    o1 = ProjectObject(project_id=p1.id, name="Корпус 1", address="ул. Строителей, 1")
    o2 = ProjectObject(project_id=p1.id, name="Корпус 2", address="ул. Строителей, 3")
    o3 = ProjectObject(project_id=p2.id, name="Паркинг", address="пр. Гранитный, 7")
    db.add_all([o1, o2, o3])
    db.flush()

    demo1 = Contractor(contract_type="Заказчик", name="ООО «Демо-Девелопер»", inn="7700000001",
                       city="Москва", legal_address="г. Москва, ул. Примерная, 1",
                       director="Петров Петр Петрович", phone="8 (495) 111-11-11",
                       email="info@demo-dev.ru", sb_status="Проверен СБ", source="Ручной")
    demo2 = Contractor(contract_type="ГП", name="ООО «Демо-Подрядчик»", inn="7700000002",
                       city="Москва", director="Сидоров Сидор Сидорович",
                       phone="8 (495) 222-22-22", email="tender@demo-podryad.ru",
                       sb_status="Средние риски", source="Ручной")
    demo3 = Contractor(contract_type="СП", name="ООО «Демо-Субподрядчик»", inn="7700000003",
                       city="Москва", director="Козлов Козел Козлович",
                       phone="8 (495) 333-33-33", email="office@demo-sub.ru", source="Ручной")
    db.add_all([demo1, demo2, demo3])
    db.flush()

    gp = Contract(contract_type="ГП", customer_id=demo1.id, gencontractor_id=demo2.id,
                  contractor_id=demo2.id, number="ГП-2026-001", date=date(2026, 1, 15),
                  project_id=p1.id, object_id=o1.id, subject="СМР", rd_section="КЖ",
                  amount=25_000_000, advance_pct=20, date_start=date(2026, 2, 1),
                  date_end=date(2026, 6, 1), status="Подписан",
                  has_ird=True, has_tz=True, has_gf=True, has_estimate=True)
    sp = Contract(contract_type="СП", parent_id=None, contractor_id=demo3.id,
                  number="СП-2026-014", date=date(2026, 2, 10), project_id=p1.id,
                  object_id=o1.id, subject="СМР", rd_section="ОВиК",
                  amount=4_500_000, advance_pct=10, date_start=date(2026, 3, 1),
                  date_end=date(2026, 5, 15), status="Подписан")
    pir = Contract(contract_type="ПИР", customer_id=demo1.id, contractor_id=demo2.id,
                   number="ПИР-2026-002", date=date(2026, 1, 20), project_id=p2.id,
                   object_id=o3.id, subject="ПИР", rd_section="АР",
                   amount=1_800_000, date_start=date(2026, 2, 5),
                   date_end=date(2026, 4, 30), status="Подписан с одной стороны")
    db.add_all([gp, sp, pir])
    db.flush()
    sp.parent_id = gp.id
    db.flush()

    for c in (gp, sp, pir):
        recalc_contract(db, c)

    db.add(ContractAmendment(contract_id=gp.id, number="ДС-1", date=date(2026, 3, 1),
                             new_amount=27_500_000, new_date_end=date(2026, 7, 1),
                             status="Проект", reason="Доп. объемы по фасаду"))
    db.commit()
    recalc_contract(db, gp)

    today = date.today()
    db.add_all([
        Payment(contract_id=gp.id, project_id=p1.id, object_id=o1.id, kind="Входящий",
                stage_type="Аванс", plan_date=date(2026, 2, 1), fact_date=date(2026, 2, 3),
                plan_sum=5_000_000, fact_sum=5_000_000, status="Оплачено"),
        Payment(contract_id=gp.id, project_id=p1.id, object_id=o1.id, kind="Входящий",
                stage_type="по КС-2", stage_label="1", plan_date=today - timedelta(days=7),
                plan_sum=3_200_000, fact_sum=0, status="Ожидание"),
        Payment(contract_id=sp.id, project_id=p1.id, object_id=o1.id, kind="Исходящий",
                stage_type="Аванс", plan_date=date(2026, 3, 1), fact_date=date(2026, 3, 4),
                plan_sum=450_000, fact_sum=450_000, status="Оплачено"),
        Payment(contract_id=sp.id, project_id=p1.id, object_id=o1.id, kind="Исходящий",
                stage_type="по КС-2", stage_label="1", plan_date=today - timedelta(days=12),
                plan_sum=900_000, fact_sum=0, status="Ожидание"),
        Payment(project_id=p2.id, object_id=o3.id, kind="Исходящий", stage_type="Прочее",
                stage_label="ПОС", plan_date=date(2026, 3, 15), plan_sum=250_000,
                fact_sum=0, status="Ожидание"),
    ])
    db.flush()  # autoflush=False — селекты ниже не видят неподтверждённые оплаты
    for p in db.execute(select(Payment)).scalars():
        recalc_payment(db, p)
    for c in (gp, sp, pir):
        recalc_contract(db, c)

    b1 = BudgetItem(project_id=p1.id, object_id=o1.id, rd_section="КЖ", article="СМР",
                    work_name="Монолитные работы корпуса 1", unit="м3",
                    qty_plan=5200, price_plan=8500, qty_fact=2100, price_fact=8450,
                    status="Действует", tender_date_start=date(2025, 12, 1),
                    tender_date_end=date(2025, 12, 20))
    b2 = BudgetItem(project_id=p1.id, object_id=o1.id, rd_section="ОВиК", article="СМР",
                    work_name="Отопление корпуса 1", unit="пог м",
                    qty_plan=1800, price_plan=3200, qty_fact=950, price_fact=3400,
                    status="Действует")
    b3 = BudgetItem(project_id=p1.id, object_id=o1.id, rd_section="АР", article="ПИР",
                    work_name="Рабочая документация фасады", unit="м2",
                    qty_plan=1, price_plan=1_200_000, qty_fact=1, price_fact=1_450_000,
                    status="Действует")
    b4 = BudgetItem(project_id=p2.id, object_id=o3.id, rd_section="ПЗ", article="Услуги",
                    work_name="Проектирование паркинга", unit="компл", qty_plan=1,
                    price_plan=980_000, status="Действует")
    db.add_all([b1, b2, b3, b4])
    for b in (b1, b2, b3, b4):
        recalc_budget_item(db, b)

    db.add(ChangeLog(user_email="seed", entity="system", action="сид",
                     details="Демо-данные созданы автоматически"))
    db.commit()
    return True


def seed_contractors_from_export(db, cap_per_sheet: int = 500) -> str:
    """Импорт топ-контрагентов (по обороту 2025) из выгрузки Синапс, если их ещё нет."""
    if db.execute(select(func.count(Contractor.id)).where(Contractor.source == "Синапс")).scalar():
        return "уже импортированы"
    if not EXPORT_XLSX.is_file():
        return "файл выгрузки не найден"
    from openpyxl import load_workbook
    from .services.contractor_import import import_workbook

    wb = load_workbook(EXPORT_XLSX, read_only=True, data_only=True)
    sheets = [s.title for s in wb.worksheets if s.title.startswith("Дмитрий")]
    created, updated, skipped = import_workbook(db, wb, cap_per_sheet=cap_per_sheet,
                                                sheet_names=sheets)
    db.commit()
    wb.close()
    return f"новых {created}, обновлено {updated} (листы: {', '.join(sheets)}, по {cap_per_sheet})"


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        print("Админ/пользователи:", "созданы" if seed_admin(db) else "уже есть")
        print("Демо-данные:", "созданы" if seed_demo(db) else "уже есть")
        print("Контрагенты из Синапс:", seed_contractors_from_export(db))
    finally:
        db.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
