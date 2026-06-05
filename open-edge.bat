@echo off
setlocal enabledelayedexpansion
title Open Edge for Collector

cd /d "%~dp0"

echo.
echo ============================================================
echo    打开采集浏览器 / Open Edge for Collector
echo ============================================================
echo.

REM Already running with debug port? Then do NOTHING - reuse current Edge.
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:9222/json/version' -UseBasicParsing -TimeoutSec 2) ^| Out-Null; exit 0 } catch { exit 1 }" > "%TEMP%\_amzchk" 2>&1
if not errorlevel 1 (
    echo   Edge 已经开启调试，无需任何操作！直接去采集即可。
    echo   Edge is already running with debugging - nothing to do.
    echo.
    pause
    exit /b 0
)

echo   需要把你的 Edge 重启一次以开启调试端口。
echo   你的登录、扩展（卖家精灵 / SIF）全部保留，用的就是你的主 Edge。
echo.
echo   这一步只在现在需要做一次。之后保持这个窗口开着，
echo   每次采集会自动连接，不会再重启。
echo.
echo   This restarts your Edge ONCE to enable the debug port.
echo   All logins and extensions are kept - it is your main Edge.
echo   Keep the window open afterwards; future runs auto-connect.
echo.
pause

REM Close existing Edge so the relaunch (with the debug flag, same profile)
REM becomes the live process and actually opens the port.
echo.
echo   正在重启 Edge ... / Restarting Edge ...
taskkill /f /im msedge.exe > "%TEMP%\_amzchk" 2>&1
ping -n 3 127.0.0.1 > "%TEMP%\_amzchk" 2>&1

REM Launch your MAIN Edge (default profile) with remote debugging enabled.
REM No --user-data-dir => uses your normal profile with all logins/extensions.
start "" "msedge.exe" "--remote-debugging-port=9222" "--no-first-run" "--no-default-browser-check" "https://www.amazon.com"

REM Wait for the debug port to open (up to ~15s)
echo   等待浏览器启动 / Waiting for Edge ...
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
    echo   完成！Edge 已就绪，现在去采集工具点「开始采集」即可。
    echo   Done! Edge is ready - go start collecting.
) else (
    echo.
    echo   [警告] 端口未打开。请确认所有 Edge 窗口都已关闭后，再运行本脚本。
    echo   [WARNING] Port did not open. Close ALL Edge windows, then run this again.
)

echo.
pause
endlocal
