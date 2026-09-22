@echo off
cd /d %~dp0
py -3.11 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
if not exist .env copy .env.example .env
echo.
echo Setup complete. Run run.bat, then open http://127.0.0.1:8000
