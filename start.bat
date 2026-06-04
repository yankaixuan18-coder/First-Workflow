@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Amazon 选品采集工具 - 启动器

cd /d "%~dp0"

echo.
echo ============================================================
echo        Amazon 选品采集工具 ^| Product Research Collector
echo ============================================================
echo.

REM ----------------------------------------------------------------
REM 1. Check Python
REM ----------------------------------------------------------------
echo [1/6] 检查 Python / Checking Python ...
set "PYTHON="
where py >nul 2>nul && set "PYTHON=py -3"
if not defined PYTHON (
    where python >nul 2>nul && set "PYTHON=python"
)
if not defined PYTHON (
    echo.
    echo [错误 ERROR] 没有找到 Python / Python is not installed.
    echo.
    echo   请先安装 Python 3.10 或更高版本：
    echo   Please install Python 3.10+ from:
    echo       https://www.python.org/downloads/
    echo.
    echo   安装时请务必勾选 "Add Python to PATH"。
    echo   During install, CHECK the box "Add Python to PATH".
    echo.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('%PYTHON% --version 2^>^&1') do set "PYVER=%%v"
echo       找到 / Found: !PYVER!
echo.

REM ----------------------------------------------------------------
REM 2. Create virtual environment if missing
REM ----------------------------------------------------------------
echo [2/6] 准备虚拟环境 / Preparing virtual environment ...
if not exist ".venv\Scripts\python.exe" (
    echo       正在创建虚拟环境 / Creating .venv ... ^(首次运行较慢^)
    %PYTHON% -m venv .venv
    if errorlevel 1 (
        echo.
        echo [错误 ERROR] 创建虚拟环境失败 / Failed to create virtual environment.
        echo   请确认 Python 安装完整 / Please ensure Python is fully installed.
        pause
        exit /b 1
    )
) else (
    echo       已存在 / Already exists.
)
set "VENV_PY=.venv\Scripts\python.exe"
echo.

REM ----------------------------------------------------------------
REM 3. Install dependencies
REM ----------------------------------------------------------------
echo [3/6] 安装依赖 / Installing dependencies ...
if not exist ".venv\.deps_installed" (
    echo       正在安装，请稍候 / Installing, please wait ... ^(首次运行需要几分钟^)
    "%VENV_PY%" -m pip install --upgrade pip >nul 2>nul
    "%VENV_PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [错误 ERROR] 依赖安装失败 / Failed to install dependencies.
        echo   请检查网络连接 / Please check your internet connection and retry.
        pause
        exit /b 1
    )
    REM Install Playwright browser driver (fallback if system Chrome is unavailable)
    echo       配置浏览器驱动 / Setting up browser driver ...
    "%VENV_PY%" -m playwright install chromium >nul 2>nul
    echo done> ".venv\.deps_installed"
    echo       依赖安装完成 / Dependencies installed.
) else (
    echo       已安装 / Already installed.
)
echo.

REM ----------------------------------------------------------------
REM 4. Load / create .env configuration
REM ----------------------------------------------------------------
echo [4/6] 检查配置文件 / Checking configuration ...
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo.
        echo [提示 NOTICE] 已为你创建 .env 配置文件 / Created .env from template.
        echo   请设置你的 Chrome 路径 / Please set your Chrome path.
        echo   即将打开记事本，编辑后请保存并关闭 / Opening Notepad — edit, save, then close it.
        echo.
        pause
        notepad ".env"
    ) else (
        echo [警告 WARNING] 没有找到 .env 或 .env.example / No .env found.
    )
) else (
    echo       配置文件已就绪 / Configuration ready.
)
echo.

REM ----------------------------------------------------------------
REM 5. Reminder: close Chrome
REM ----------------------------------------------------------------
echo [5/6] 重要提醒 / Important reminder
echo.
echo   ^>^>^> 运行前请完全关闭所有 Chrome 窗口 ^<^<^<
echo   ^>^>^> Please CLOSE all Chrome windows before collecting ^<^<^<
echo.

REM ----------------------------------------------------------------
REM 6. Launch app + open browser
REM ----------------------------------------------------------------
echo [6/6] 启动程序 / Starting the app ...
echo.
echo   本地地址 / Local address:  http://localhost:5000
echo   关闭此窗口即可停止程序 / Close this window to stop the app.
echo.

REM Open the browser shortly after the server starts
start "" /b cmd /c "timeout /t 3 >nul & start "" http://localhost:5000"

REM Run the Flask app in the foreground (keeps this window open)
"%VENV_PY%" main.py

echo.
echo 程序已停止 / The app has stopped.
pause
endlocal
