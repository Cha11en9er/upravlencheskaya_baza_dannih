# УБД — Управленческая база данных (МВП)

МВП сайта по ТЗ `Dmitiy_stroitelnaya_kompaniya/docs/ТЗ от 01.03.docx` (v6.0):
авторизация с ролями и правами на блоки, Главная с плитками, Бюджет, Договоры ГП/СП
с ДС, Оплаты, Карточка контрагента с импортом из Excel, Отчеты, Админ-панель
(пользователи/проекты/журнал изменений), экспорт в XLSX.

## Быстрый старт

```
# 1. Запуск сервера (двойной клик):
run_ubd.bat

# 2. Открыть в браузере:
http://127.0.0.1:8000

# 3. Войти:
Администратор:  admin@ubd.local / admin123
РП (демо):      rp@ubd.local   / user123
Финансист(демо): fin@ubd.local / user123
```

Первый запуск: при пустой базе автоматически создаётся админ (`UBD_ADMIN_EMAIL` /
`UBD_ADMIN_PASSWORD` из `ubd/backend/.env`) — **смени пароль в админ-панели**.

## Структура

```
ubd/
  backend/
    app/
      main.py          — приложение FastAPI
      config.py        — настройки (UBD_* переменные / .env)
      models.py        — модели SQLAlchemy (9 таблиц)
      security.py      — пароли pbkdf2 + JWT
      permissions.py   — 17 ролей, 9 блоков, уровни edit/read/none
      calc.py          — калькуляции ТЗ (пени, просрочка, риски) — покрыты тестами
      services/        — пересчёты, журнал изменений, экспорт XLSX, импорт Excel
      routers/         — auth, dashboard, contracts, payments, budget,
                         contractors, reports, admin
      seed.py          — сид админа/демо + импорт топ-контрагентов из базы Синапс
    scripts/make_pg_db.py — переход на PostgreSQL (см. docs/SETUP.md)
    tests/             — pytest: калькуляции, права, сценарии (22 теста)
    requirements.txt   — закреплённые версии
  frontend/
    templates/         — Jinja2 (16 шаблонов)
    static/css, static/js — свои стили и скрипты, ноль внешних CDN
  docs/
    DECISIONS.md  SETUP.md  MVP_SCOPE.md  PROGRESS.md
```

## Данные

Справочник контрагентов наполняется кнопкой «Импорт из Excel» (Договоры → Контрагенты)
из выгрузки `export/девелоперы_генподрядчики_синапс.xlsx`; при сиде уже импортированы
топ-1000 (по 500 девелоперов и генподрядчиков с оборотом и контактами).

## Тесты

```
cd ubd\backend
..\.venv\Scripts\python.exe -m pytest tests -q
```

Подробнее: `ubd/docs/DECISIONS.md` (почему так), `MVP_SCOPE.md` (что вошло/не вошло),
`SETUP.md` (окружение и переход на PostgreSQL), `PROGRESS.md` (журнал сборки).
