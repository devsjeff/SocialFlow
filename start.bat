@echo off
REM One-click launcher: opens the Python API and the Next.js UI in two windows.
cd /d "%~dp0"

if not exist ".env" copy ".env.example" ".env" >nul

if not exist "backend\.venv" (
  echo Creating Python environment...
  python -m venv backend\.venv
  backend\.venv\Scripts\python -m pip install -q -r backend\requirements.txt
)
if not exist "frontend\node_modules" (
  echo Installing frontend packages...
  pushd frontend
  call npm install
  popd
)

start "Scheduler API (8000)" cmd /k "cd /d %~dp0backend && .venv\Scripts\python -m uvicorn app.main:app --reload --port 8000"
start "Scheduler UI (3000)" cmd /k "cd /d %~dp0frontend && npm run dev"
timeout /t 6 >nul
start http://localhost:3000
