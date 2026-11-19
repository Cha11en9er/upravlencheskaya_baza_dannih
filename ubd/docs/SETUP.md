# Окружение и установка (что было на машине и что я сделал)

Дата: 2026-11-19, машина Windows 10, всё локально.

## Разведка окружения (проверено командами)

| Компонент | Статус |
|---|---|
| Python | 3.12.0 (`C:\Users\Miroslav\AppData\Local\Programs\Python\Python312`) |
| pip | 24.0 |
| PostgreSQL 18 | **служба postgresql-x64-18 запущена**, слушает 127.0.0.1:5432 |
| psql/pg_isready | не в PATH; бинарники в `C:\Program Files\PostgreSQL\18\bin` |
| Доступ к PG | pg_hba.conf: только scram-sha-256; пароль postgres неизвестен, `postgres/postgres` не подошёл. Перебор паролей не проводился |
| PyPI | доступен (pip index versions fastapi) |
| node | v22.16.0 (не используется: фронт без сборки) |
| Порт 8000 | свободен |

## Что сделано

1. `python -m venv ubd/.venv` + `pip install` закреплённых версий из
   официального PyPI (список → `backend/requirements.txt`; `pip freeze`:
   fastapi 0.165.0, starlette 1.10.0, SQLAlchemy 2.1.9, psycopg 3.3.9,
   pydantic 2.14.4, PyJWT 2.15.1, Jinja2 3.1.6, python-multipart 0.0.34,
   openpyxl 3.1.5, uvicorn 0.54.0, pytest 9.2.0, httpx2 2.16.2).
2. `ubd/backend/.env` создан с UBD_SECRET_KEY (secrets.token_urlsafe(48)) и
   UBD_DB_URL на SQLite. Шаблон — `ubd/backend/.env.example`.
3. База `ubd/backend/ubd.db` создана сидом `python -m app.seed`:
   - 3 пользователя (админ + РП + Финансист),
   - демо-данные: 2 проекта, 3 объекта, 3 демо-контрагента, 3 договора
     (ГП+СП+ПИР), 5 оплат (с просрочками), 4 строки бюджета, ДС,
   - **998 контрагентов** из реальной базы: топ-500 девелоперов + топ-500
     генподрядчиков из `export/девелоперы_генподрядчики_синапс.xlsx`
     (с оборотом 2025, телефонами, почтой, городом, СРО).

## Переход на PostgreSQL (когда будет пароль)

```powershell
cd C:\repos\YouDo\Dmitiy_stroitelnaya_kompaniya\ubd\backend
..\.venv\Scripts\python.exe scripts\make_pg_db.py <пароль_postgres>
# скрипт напечатает строку UBD_DB_URL=postgresql+psycopg://ubd_app:...@127.0.0.1:5432/ubd
# 1) впиши её в ubd/backend/.env (замени SQLite-строку)
# 2) удали/переименуй ubd.db (или оставь — она просто перестанет использоваться)
# 3) запусти run_ubd.bat — таблицы создадутся, сид (админ + импорт) выполнится сам
```

Роль `ubd_app` создаётся только под базу `ubd` (не superuser). psycopg[binary]
уже в requirements.

## Запуск / проверка

```
run_ubd.bat                       → http://127.0.0.1:8000
cd ubd\backend
..\.venv\Scripts\python.exe -m pytest tests -q      # 22 passed
..\.venv\Scripts\python.exe -m app.seed             # сид идемпотентен
```

## Известные ограничения МВП

- SQLite держит несколько читателей и сериализует запись — для 10-30
  пользователей одновременно это «начало тормозов»; переход на PG обязателен
  при реальном многопользовательском использовании.
- Пароли пользователей создаются админом; смену своего пароля пользователем
  планируется в следующем спринте.
