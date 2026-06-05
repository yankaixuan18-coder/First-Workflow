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

REM ---------- 5. Check Edge debug port ----------
echo [5/6] Checking Edge debug port 9222 ...
echo.

powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:9222/json/version' -UseBasicParsing -TimeoutSec 2) ^| Out-Null; exit 0 } catch { exit 1 }" > "%TEMP%\_amzchk" 2>&1
if not errorlevel 1 (
    echo       采集浏览器已就绪。/ Collector browser is ready.
) else (
    echo       采集浏览器未启动。
    echo.
    echo   *** 请先运行 open-edge.bat 打开采集专用浏览器！***
    echo   *** Please run open-edge.bat first to open the collector browser! ***
    echo.
    echo   open-edge.bat 在同一个文件夹里，双击即可。
    echo   采集浏览器只需打开一次，之后保持开着就行。
    echo.
)
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
