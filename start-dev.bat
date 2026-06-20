@echo off
chcp 65001 >nul 2>nul
setlocal

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "FRONTEND_DIR=%ROOT%\frontend"

where uv >nul 2>nul
if errorlevel 1 (
  echo [ERROR] uv was not found.
  echo Install uv: https://docs.astral.sh/uv/getting-started/installation/
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm was not found.
  echo Install Node.js: https://nodejs.org/
  exit /b 1
)

echo ========================================
echo   Buping - AI Career Assistant
echo ========================================
echo.

echo [1/3] Syncing backend dependencies with uv ...
pushd "%ROOT%"
call uv sync
if errorlevel 1 (
  echo [ERROR] uv sync failed.
  popd
  exit /b 1
)
popd

if not exist "%FRONTEND_DIR%\node_modules" (
  echo [2/3] Installing frontend dependencies ...
  pushd "%FRONTEND_DIR%"
  call npm install
  if errorlevel 1 (
    echo [ERROR] npm install failed.
    popd
    exit /b 1
  )
  popd
) else (
  echo [2/3] Frontend dependencies already installed.
)

echo [3/3] Starting Buping ...
echo.
cd /d "%ROOT%"
set PYTHONUNBUFFERED=1
call uv run python -m backend.dev_launcher

endlocal
