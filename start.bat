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
    echo EDGE_CDP_URL=http://127.0.0.1:9222
    echo.
    echo ANTHROPIC_API_KEY=
    echo OPENAI_API_KEY=
    echo GEMINI_API_KEY=
    echo DEEPSEEK_API_KEY=
) > ".env"
echo       Edge path: !EDGE_DIR!
echo.

REM ---------- 5. Ensure Edge debug port 9222 is available ----------
echo [5/6] Checking Edge remote debugging port 9222 ...
echo.

REM First: is the debug port ALREADY open? If so, do NOT touch Edge at all —
REM just reuse the browser you already have open (no restart, logins kept).
set "PORT_OK="
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:9222/json/version' -UseBasicParsing -TimeoutSec 2) ^| Out-Null; exit 0 } catch { exit 1 }" > "%TEMP%\_amzchk" 2>&1
if not errorlevel 1 set "PORT_OK=1"

if defined PORT_OK (
    echo       Edge is already running with debugging enabled.
    echo       Your current browser will be reused - it will NOT be restarted.
    echo.
    goto :EDGE_READY
)

REM Port is not open yet. We must start Edge once with the debug flag.
REM Because Edge uses a single shared process per profile, any Edge window
REM that is open WITHOUT the debug flag must be closed first - otherwise the
REM new --remote-debugging-port launch just attaches to it and the port never
REM opens. This one-time restart is only needed when the port is not up.
echo   The debug port is not open yet, so Edge needs to be started ONCE
echo   with debugging enabled. All your logins and extensions
echo   (SellerSprite / SIF) are kept - this uses your normal profile.
echo.
echo   NOTE: This one-time restart is only needed now. After this, the
echo   browser stays open and every later collection reuses it directly.
echo.

REM Close existing Edge so the debug-enabled launch becomes the live process.
taskkill /f /im msedge.exe > "%TEMP%\_amzchk" 2>&1
ping -n 3 127.0.0.1 > "%TEMP%\_amzchk" 2>&1

REM Launch Edge with remote debugging enabled (default profile -> keeps logins)
start "" "msedge.exe" "--remote-debugging-port=9222" "--no-first-run" "--no-default-browser-check"

REM Wait until the debug port actually answers on 127.0.0.1 (up to ~15s).
echo       Waiting for Edge debug port 9222 ...
for /l %%i in (1,1,15) do (
    if not defined PORT_OK (
        powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:9222/json/version' -UseBasicParsing -TimeoutSec 2) ^| Out-Null; exit 0 } catch { exit 1 }" > "%TEMP%\_amzchk" 2>&1
        if not errorlevel 1 set "PORT_OK=1"
        if not defined PORT_OK ping -n 2 127.0.0.1 > "%TEMP%\_amzchk" 2>&1
    )
)

if defined PORT_OK (
    echo       Edge debug port 9222 is ready.
) else (
    echo.
    echo [WARNING] Edge debug port 9222 did NOT open.
    echo   Please CLOSE ALL Edge windows completely, then run start.bat again.
    echo.
)

:EDGE_READY
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
