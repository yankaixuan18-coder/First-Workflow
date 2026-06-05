@echo off
setlocal enabledelayedexpansion
title Open Tool Browser - Amazon Collector

cd /d "%~dp0"

echo.
echo ============================================================
echo    打开采集专用浏览器 / Open Collector Browser
echo ============================================================
echo.

REM Check if the debug port is already live — if so, nothing to do.
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:9222/json/version' -UseBasicParsing -TimeoutSec 2) ^| Out-Null; exit 0 } catch { exit 1 }" > "%TEMP%\_amzchk" 2>&1
if not errorlevel 1 (
    echo   采集浏览器已经在运行！直接回到采集工具点「开始采集」即可。
    echo   The collector browser is already running - just start collecting.
    echo.
    pause
    exit /b 0
)

REM Profile stored inside the project folder — completely separate from your
REM main Edge profile, so it runs alongside it with no conflicts.
set "PROFILE_DIR=%~dp0browser-profile"
if not exist "!PROFILE_DIR!" mkdir "!PROFILE_DIR!"

echo   正在打开采集专用Edge浏览器...
echo   Opening dedicated Edge browser for the collector...
echo.
echo   ┌─────────────────────────────────────────────────────┐
echo   │  首次使用请在弹出的Edge窗口中完成：                │
echo   │  1. 安装 卖家精灵 扩展（Edge扩展商店搜索）        │
echo   │  2. 安装 SIF 扩展                                   │
echo   │  3. 登录 Amazon 账号                                │
echo   │  完成后保持这个窗口开着，以后每次采集会自动连接。  │
echo   │                                                      │
echo   │  First-time setup in the Edge window that opens:    │
echo   │  1. Install SellerSprite extension                  │
echo   │  2. Install SIF extension                           │
echo   │  3. Log into Amazon                                 │
echo   │  Keep this window open — future runs auto-connect.  │
echo   └─────────────────────────────────────────────────────┘
echo.

start "" "msedge.exe" ^
    "--user-data-dir=!PROFILE_DIR!" ^
    "--remote-debugging-port=9222" ^
    "--no-first-run" ^
    "--no-default-browser-check" ^
    "https://www.amazon.com"

REM Wait for the debug port to open (up to 15s)
echo   等待浏览器启动 / Waiting for browser to start ...
set "PORT_OK="
for /l %%i in (1,1,15) do (
    if not defined PORT_OK (
        powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:9222/json/version' -UseBasicParsing -TimeoutSec 2) ^| Out-Null; exit 0 } catch { exit 1 }" > "%TEMP%\_amzchk" 2>&1
        if not errorlevel 1 set "PORT_OK=1"
        if not defined PORT_OK ping -n 2 127.0.0.1 > "%TEMP%\_amzchk" 2>&1
    )
)

if defined PORT_OK (
    echo.
    echo   浏览器已就绪！/ Browser is ready!
    echo   现在可以回到采集工具（http://localhost:5000）开始采集。
    echo   You can now go to http://localhost:5000 and start collecting.
) else (
    echo.
    echo   [WARNING] 浏览器启动超时，请手动确认Edge已打开。
)

echo.
pause
endlocal
