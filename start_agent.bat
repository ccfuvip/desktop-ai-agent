@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ===================================================================
echo   🤖 启动桌面AI Agent
echo ===================================================================
echo.

REM 检查Python环境
echo [检查] Python环境...
where python >nul 2>&1
if errorlevel 1 (
    echo ❌ Python 未找到！
    pause
    exit /b 1
)

REM 检查依赖
echo [检查] 依赖库...
python -c "import PyQt6, mss, uiautomation, pyautogui, keyboard, chromadb, httpx" 2>nul
if errorlevel 1 (
    echo ⚠️  部分依赖未安装，正在安装...
    pip install -r requirements.txt --quiet
    echo ✅ 依赖安装完成
)

echo.
echo [提示] 请确保已启动本地模型服务
echo        运行: start_servers.bat
echo.
echo ===================================================================
echo   🖥️  Agent即将启动...
echo ===================================================================
echo.

REM 启动主程序
python ui_main.py

echo.
echo ⚠️  Agent已关闭
pause
