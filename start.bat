@echo off
setlocal enabledelayedexpansion
title Amazon Product Research Collector - Launcher

cd /d "%~dp0"

echo.
echo ============================================================
echo    Amazon Product Research Collector
echo ============================================================
echo.

REM ---------- 1. Check Python ----------
echo [1/6] Checking Python ...
set "PYTHON="
where py > "%TEMP%\_amzchk" 2>&1 && set "PYTHON=py -3"
if not defined PYTHON where python > "%TEMP%\_amzchk" 2>&1 && set "PYTHON=python"
if not defined PYTHON (
    echo.
    echo [ERROR] Python was not found.
    echo.
    echo   Please install Python 3.10+ from:
    echo       https://www.python.org/downloads/
    echo.
    echo   During install, CHECK the box "Add Python to PATH".
    echo.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('%PYTHON% --version 2^>^&1') do set "PYVER=%%v"
echo       Found: !PYVER!
echo.

REM ---------- 2. Virtual environment ----------
echo [2/6] Preparing virtual environment ...
if not exist ".venv\Scripts\python.exe" (
    echo       Creating .venv ... (first run is slower)
    %PYTHON% -m venv .venv
    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo       Already exists.
)
set "VENV_PY=.venv\Scripts\python.exe"
echo.

REM ---------- 3. Dependencies ----------
echo [3/6] Installing dependencies ...
if not exist ".venv\.deps_installed" (
    echo       Installing, please wait ... (first run takes a few minutes)
    "%VENV_PY%" -m pip install --upgrade pip
    "%VENV_PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to install dependencies. Check your internet connection.
        pause
        exit /b 1
    )
    echo       Browser driver ready (using your installed Microsoft Edge).
    echo done> ".venv\.deps_installed"
    echo       Dependencies installed.
) else (
    echo       Already installed.
)
echo.

REM ---------- 4. Configuration ----------
echo [4/6] Checking configuration ...
set "EDGE_DIR=%LOCALAPPDATA%\Microsoft\Edge\User Data"
REM Always regenerate .env to ensure correct variable names
(
    echo CHROME_USER_DATA_DIR=!EDGE_DIR!
    echo CHROME_PROFILE=Default
    echo EDGE_USE_CDP=true
    echo EDGE_CDP_URL=http://localhost:9222
    echo.
    echo ANTHROPIC_API_KEY=
    echo OPENAI_API_KEY=
    echo GEMINI_API_KEY=
    echo DEEPSEEK_API_KEY=
) > ".env"
echo       Edge path: !EDGE_DIR!
echo.

REM ---------- 5. Launch Edge with remote debugging ----------
echo [5/6] Starting Edge with remote debugging port 9222 ...
echo.
echo   Your existing Edge browser with all logins and extensions
echo   (SellerSprite / SIF) will be used automatically.
echo.
echo   NOTE: If Edge is already open, close it first, then this
echo   script will reopen it with debugging enabled.
echo.

REM Kill any lingering Edge processes that don't have the debug port
REM (silent - if nothing to kill, that is fine)
taskkill /f /im msedge.exe > "%TEMP%\_amzchk" 2>&1

REM Wait a moment for processes to fully exit
ping -n 3 127.0.0.1 > "%TEMP%\_amzchk" 2>&1

REM Launch Edge with remote debugging enabled
REM --user-data-dir is NOT set here so Edge uses its default profile automatically
start "" "msedge.exe" "--remote-debugging-port=9222" "--no-first-run" "--no-default-browser-check"

REM Wait for Edge to start and open the debug port
ping -n 4 127.0.0.1 > "%TEMP%\_amzchk" 2>&1

echo       Edge started with remote debugging on port 9222.
echo.

REM ---------- 6. Launch Flask app ----------
echo [6/6] Starting the app ...
echo.
echo   Local address:  http://localhost:5000
echo   Close this window to stop the app.
echo.
start "" /b powershell -NoProfile -Command "Start-Sleep -Seconds 3; Start-Process 'msedge.exe' 'http://localhost:5000'"
"%VENV_PY%" main.py
echo.
echo The app has stopped.
pause
endlocal
