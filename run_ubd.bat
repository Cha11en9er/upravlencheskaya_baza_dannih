@echo off
rem УБД МВП — запуск локального сервера
rem Сайт откроется на http://127.0.0.1:8000
cd /d "%~dp0ubd\backend"
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
