"""Модели данных УБД (МВП по ТЗ v6.0, деньги — целые рубли без копеек, как в ТЗ п.9.2)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True)
    full_name: Mapped[str] = mapped_column(String(160), default="")
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(40), default="Пользователь")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # {block_key: "edit"|"read"|"none"} — уровень доступа к каждому блоку (ТЗ 1.2 п.2)
    block_access: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="Действует")  # Действует/Закрыт
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    objects: Mapped[list["ProjectObject"]] = relationship(back_populates="project", cascade="all,delete-orphan")


class ProjectObject(Base):
    __tablename__ = "project_objects"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(300), default="")

    project: Mapped[Project] = relationship(back_populates="objects")


class Contractor(Base):
    """Карточка контрагента (ТЗ 3.2.6) + поля обогащения из Синапс."""
    __tablename__ = "contractors"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_type: Mapped[str] = mapped_column(String(30), default="Прочие")  # Заказчик/ГП/СП/Поставщик/Проектировщик/Оператор/Прочие
    name: Mapped[str] = mapped_column(String(250), index=True)
    inn: Mapped[str] = mapped_column(String(12), index=True, default="")
    kpp: Mapped[str] = mapped_column(String(12), default="")
    ogrn: Mapped[str] = mapped_column(String(15), default="")
    bik: Mapped[str] = mapped_column(String(12), default="")
    checking_account: Mapped[str] = mapped_column(String(30), default="")
    corr_account: Mapped[str] = mapped_column(String(30), default="")
    legal_address: Mapped[str] = mapped_column(String(400), default="")
    physical_address: Mapped[str] = mapped_column(String(400), default="")
    director: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(300), default="")
    city: Mapped[str] = mapped_column(String(120), default="")
    sb_status: Mapped[str] = mapped_column(String(30), default="")  # Проверен СБ / Средние риски / Высокие риски
    work_type_rd: Mapped[str] = mapped_column(String(60), default="")
    # Обогащение из Синапс (сверх ТЗ, для обзвона)
    revenue_2025: Mapped[int | None] = mapped_column(Integer, nullable=True)
    egrul_status: Mapped[str] = mapped_column(String(40), default="")
    sro_name: Mapped[str] = mapped_column(String(300), default="")
    source: Mapped[str] = mapped_column(String(20), default="Ручной")  # Ручной / Синапс
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Contract(Base):
    """Договор ГП/СП (ТЗ 3.2.3). Суммы — целые рубли."""
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_type: Mapped[str] = mapped_column(String(20), default="ГП")  # ГП/СП/ПИР/МТО/Услуги/Прочее
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"), nullable=True)  # ID ГП для СП
    parent: Mapped["Contract | None"] = relationship(remote_side="Contract.id", foreign_keys=[parent_id])
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("contractors.id"), nullable=True)  # Заказчик
    gencontractor_id: Mapped[int | None] = mapped_column(ForeignKey("contractors.id"), nullable=True)  # Генподрядчик
    subcontractor_id: Mapped[int | None] = mapped_column(ForeignKey("contractors.id"), nullable=True)  # Подрядчик
    contractor_id: Mapped[int | None] = mapped_column(ForeignKey("contractors.id"), nullable=True)  # Контрагент-исполнитель
    contractor: Mapped["Contractor | None"] = relationship(foreign_keys=[contractor_id])
    number: Mapped[str] = mapped_column(String(60), index=True)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    object_id: Mapped[int | None] = mapped_column(ForeignKey("project_objects.id"), nullable=True)
    subject: Mapped[str] = mapped_column(String(20), default="СМР")  # ПИР/СМР/МТР/Услуга/Прочее
    rd_section: Mapped[str] = mapped_column(String(40), default="")
    amount: Mapped[int] = mapped_column(Integer, default=0)
    advance_pct: Mapped[int] = mapped_column(Integer, default=0)  # %
    date_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="Проект")  # Проект/Подписан с одной стороны/Подписан/Аннулирован/Архив
    has_template: Mapped[bool] = mapped_column(Boolean, default=False)
    has_ird: Mapped[bool] = mapped_column(Boolean, default=False)
    has_tz: Mapped[bool] = mapped_column(Boolean, default=False)
    has_gf: Mapped[bool] = mapped_column(Boolean, default=False)
    has_gpr: Mapped[bool] = mapped_column(Boolean, default=False)
    has_estimate: Mapped[bool] = mapped_column(Boolean, default=False)
    has_rd_vpr: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(400), default="")
    # расчётные поля (пересчитываются сервисом)
    advance_sum: Mapped[int] = mapped_column(Integer, default=0)
    paid: Mapped[int] = mapped_column(Integer, default=0)
    rest: Mapped[int] = mapped_column(Integer, default=0)
    overdue_days: Mapped[int] = mapped_column(Integer, default=0)
    penalty: Mapped[int] = mapped_column(Integer, default=0)
    risk: Mapped[str] = mapped_column(String(10), default="green")  # green/yellow/red
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    amendments: Mapped[list["ContractAmendment"]] = relationship(back_populates="contract", cascade="all,delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="contract")


class ContractAmendment(Base):
    """Дополнительное соглашение (ТЗ 3.2.3.4). Подписанное ДС обновляет сумму/срок договора."""
    __tablename__ = "contract_amendments"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"))
    number: Mapped[str] = mapped_column(String(60), default="")
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    new_amount: Mapped[int] = mapped_column(Integer, default=0)
    new_date_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Проект")  # Проект/Подписан/Аннулирован
    reason: Mapped[str] = mapped_column(String(300), default="")
    contract: Mapped[Contract] = relationship(back_populates="amendments")


class Payment(Base):
    """Оплата (объединяет вкладку 3.2.4 «Оплаты и графики» и блок 3.3 «Оплаты»)."""
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"), nullable=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    object_id: Mapped[int | None] = mapped_column(ForeignKey("project_objects.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(12), default="Исходящий")  # Входящий/Исходящий
    stage_type: Mapped[str] = mapped_column(String(30), default="Прочее")  # Аванс/по КС-2/ГУ/Этап по графику/Прочее
    stage_label: Mapped[str] = mapped_column(String(60), default="")  # № этапа
    plan_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    fact_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    plan_sum: Mapped[int] = mapped_column(Integer, default=0)
    fact_sum: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="Ожидание")  # Ожидание/Оплачено/Просрочено
    note: Mapped[str] = mapped_column(String(300), default="")
    # расчётные
    overdue_days: Mapped[int] = mapped_column(Integer, default=0)
    risk: Mapped[str] = mapped_column(String(10), default="green")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    contract: Mapped[Contract | None] = relationship(back_populates="payments")


class BudgetItem(Base):
    """Бюджет (ТЗ 3.1)."""
    __tablename__ = "budget_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    object_id: Mapped[int | None] = mapped_column(ForeignKey("project_objects.id"), nullable=True)
    rd_section: Mapped[str] = mapped_column(String(40), default="")
    article: Mapped[str] = mapped_column(String(20), default="СМР")  # ИРД/ПИР/СМР/МТО/Услуги/Прочие
    work_name: Mapped[str] = mapped_column(String(300), default="")
    unit: Mapped[str] = mapped_column(String(10), default="шт")  # м2/м3/га/пог м/шт/компл
    qty_plan: Mapped[float] = mapped_column(default=0.0)
    price_plan: Mapped[int] = mapped_column(Integer, default=0)
    qty_fact: Mapped[float] = mapped_column(default=0.0)
    price_fact: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(20), default="Действует")  # Действует/Аннулирован
    tender_date_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    tender_date_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # = тендер конец + 14 к.д. (ТЗ 3.1.2)
    work_date_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    work_date_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    commissioning_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # расчётные
    sum_plan: Mapped[int] = mapped_column(Integer, default=0)
    sum_fact: Mapped[int] = mapped_column(Integer, default=0)
    deviation: Mapped[int] = mapped_column(Integer, default=0)
    deviation_pct: Mapped[float] = mapped_column(default=0.0)
    risk: Mapped[str] = mapped_column(String(10), default="green")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChangeLog(Base):
    """Журнал изменений (ТЗ 1.1 п.5)."""
    __tablename__ = "change_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    user_email: Mapped[str] = mapped_column(String(120), default="")
    entity: Mapped[str] = mapped_column(String(40), default="")
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(30), default="")
    details: Mapped[str] = mapped_column(Text, default="")


# Уникальность ИНН у импортированных из Синапс контрагентов не требуем (пустые ИНН у части),
# но индекс есть. Уникальная пара (проект, код) уже обеспечена Project.code unique.
_ = UniqueConstraint
