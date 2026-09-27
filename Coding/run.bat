@echo off
cd /d %~dp0
if not exist .venv\Scripts\activate.bat (
  echo Missing .venv. Run setup.bat first.
  exit /b 1
)
call .venv\Scripts\activate.bat
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
