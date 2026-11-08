@echo off
rem Thiqa: setup + start on Windows (double-click or run in cmd)
cd /d %~dp0
rem free port 8000 if an older Thiqa server is still running
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr LISTENING') do taskkill /F /PID %%p >nul 2>nul
set PY=python
where py >nul 2>nul && set PY=py -3
if not exist .venv %PY% -m venv .venv
.venv\Scripts\python -m pip install -q -r requirements.txt
.venv\Scripts\python -m pip install -q -r requirements-ml.txt || echo [info] ML fraud signal disabled (scikit-learn not installed)
.venv\Scripts\python tools\init_env.py
echo.
echo Visiteur: http://localhost:8000/app   Equipe: http://localhost:8000/app/#/ops   Hack: http://localhost:8000/app/#/hack
.venv\Scripts\python -m uvicorn thiqa.api:app --host 0.0.0.0 --port 8000
