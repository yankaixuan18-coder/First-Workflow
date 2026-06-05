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

REM ---------- 5. Start tool browser (copy of your logged-in Edge) ----------
echo [5/6] Starting Edge for the collector ...
echo.

set "TOOL_PROFILE=%~dp0browser-profile"
set "MAIN_PROFILE=%LOCALAPPDATA%\Microsoft\Edge\User Data"

REM If the debug port is already live, the tool browser is open - reuse it.
set "PORT_OK="
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:9222/json/version' -UseBasicParsing -TimeoutSec 2) ^| Out-Null; exit 0 } catch { exit 1 }" > "%TEMP%\_amzchk" 2>&1
if not errorlevel 1 set "PORT_OK=1"

if defined PORT_OK goto :BROWSER_READY

REM First time only: copy your CURRENT logged-in Edge profile (logins +
REM SellerSprite/SIF extensions) into the tool profile, so you never log in
REM again. The copy needs Edge closed for a moment to avoid locked files.
if not exist "!TOOL_PROFILE!\Default\Preferences" (
    echo       首次使用：正在复制你当前已登录的 Edge（登录和扩展都带过来，无需重新登录）...
    echo       First run: copying your logged-in Edge profile ^(logins + extensions^) ...
    echo       为了完整复制，需要先关闭 Edge 几秒钟。
    taskkill /f /im msedge.exe > "%TEMP%\_amzchk" 2>&1
    ping -n 3 127.0.0.1 > "%TEMP%\_amzchk" 2>&1
    if not exist "!TOOL_PROFILE!" mkdir "!TOOL_PROFILE!"
    REM Copy profile, skipping large/locked cache folders for speed.
    robocopy "!MAIN_PROFILE!" "!TOOL_PROFILE!" /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP ^
        /XD "Cache" "Code Cache" "GPUCache" "Service Worker" "DawnCache" "GrShaderCache" "ShaderCache" ^
        /XF "lockfile" "SingletonLock" "SingletonCookie" "SingletonSocket" > "%TEMP%\_amzchk" 2>&1
    echo       复制完成。你现在可以重新打开你平时用的 Edge，不受影响。
    echo.
)

echo       正在打开采集浏览器（独立窗口，和你的主 Edge 并行，互不干扰）...
start "" "msedge.exe" "--user-data-dir=!TOOL_PROFILE!" "--remote-debugging-port=9222" "--no-first-run" "--no-default-browser-check" "https://www.amazon.com"

for /l %%i in (1,1,15) do (
    if not defined PORT_OK (
        powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:9222/json/version' -UseBasicParsing -TimeoutSec 2) ^| Out-Null; exit 0 } catch { exit 1 }" > "%TEMP%\_amzchk" 2>&1
        if not errorlevel 1 set "PORT_OK=1"
        if not defined PORT_OK ping -n 2 127.0.0.1 > "%TEMP%\_amzchk" 2>&1
    )
)

:BROWSER_READY
if defined PORT_OK (
    echo       采集浏览器已就绪。/ Collector browser ready.
) else (
    echo       [警告] 浏览器端口未开启，请关闭所有 Edge 窗口后重试。
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
