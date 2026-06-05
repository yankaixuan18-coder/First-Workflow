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
    echo EDGE_USE_CDP=false
    echo EDGE_CDP_URL=http://127.0.0.1:9222
    echo.
    echo ANTHROPIC_API_KEY=
    echo OPENAI_API_KEY=
    echo GEMINI_API_KEY=
    echo DEEPSEEK_API_KEY=
) > ".env"
echo       Edge path: !EDGE_DIR!
echo.

REM ---------- 5. Prepare tool browser profile (copy of your logged-in Edge) ----------
echo [5/6] Preparing the collector browser profile ...
echo.

set "TOOL_PROFILE=%~dp0browser-profile"
set "MAIN_PROFILE=%LOCALAPPDATA%\Microsoft\Edge\User Data"

REM First time only: copy your CURRENT logged-in Edge profile (logins +
REM SellerSprite/SIF extensions) into the tool profile, so you never log in
REM again. The copy needs Edge closed for a moment to avoid locked files.
REM The app itself launches this profile when collecting (no debug port needed),
REM so it runs ALONGSIDE your normal Edge without conflicts.
if not exist "!TOOL_PROFILE!\Default\Preferences" (
    echo   ============================================================
    echo     首次使用 / First-time setup
    echo   ============================================================
    echo.
    echo   工具要把你“当前已登录”的 Edge 复制一份给采集用，
    echo   这样你就不用重新登录，卖家精灵 / SIF 扩展也一起带过来。
    echo.
    echo   复制时需要把 Edge 关闭几秒钟（之后可以马上重新打开）。
    echo   *** 请先保存好正在浏览的网页内容，再继续。***
    echo.
    echo   The tool will copy your CURRENT logged-in Edge profile so you
    echo   never log in again. Edge must close for a few seconds to copy.
    echo   *** Please save any open work in Edge before continuing. ***
    echo.
    echo   按任意键开始复制（或直接关闭本窗口取消）...
    echo   Press any key to start copying ^(or close this window to cancel^) ...
    pause > nul
    echo.
    echo       正在关闭 Edge 并复制... / Closing Edge and copying ...
    taskkill /f /im msedge.exe > "%TEMP%\_amzchk" 2>&1
    ping -n 3 127.0.0.1 > "%TEMP%\_amzchk" 2>&1
    if not exist "!TOOL_PROFILE!" mkdir "!TOOL_PROFILE!"
    REM Copy profile, skipping large/locked cache folders for speed.
    robocopy "!MAIN_PROFILE!" "!TOOL_PROFILE!" /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP ^
        /XD "Cache" "Code Cache" "GPUCache" "Service Worker" "DawnCache" "GrShaderCache" "ShaderCache" ^
        /XF "lockfile" "SingletonLock" "SingletonCookie" "SingletonSocket" > "%TEMP%\_amzchk" 2>&1
    echo       复制完成！你现在可以重新打开平时用的 Edge，完全不受影响。
    echo       Copy done. You can reopen your normal Edge now - unaffected.
    echo.
) else (
    echo       采集浏览器配置已就绪（复用上次的副本）。
    echo       Collector profile ready ^(reusing previous copy^).
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
