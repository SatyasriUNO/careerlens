@echo off
REM CareerLens - starts backend and frontend in two windows, then opens the browser.
cd /d "%~dp0"
if not exist "backend\venv\Scripts\activate.bat" (
  echo Backend is not set up yet. Follow README.md section 3 first.
  pause
  exit /b 1
)
if not exist "frontend\node_modules" (
  echo Frontend is not set up yet. Follow README.md section 4 first.
  pause
  exit /b 1
)
start "CareerLens Backend" cmd /k "cd backend && call venv\Scripts\activate.bat && uvicorn main:app --port 8000"
start "CareerLens Frontend" cmd /k "cd frontend && npm run dev"
echo Waiting for both servers to start...
timeout /t 10 /nobreak >nul
start "" http://localhost:5173
