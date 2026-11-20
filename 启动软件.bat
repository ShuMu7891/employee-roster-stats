@echo off
chcp 65001 >nul
title 员工花名册统计系统
cd /d "%~dp0"

echo 正在检查运行环境 ...
if not exist ".venv\Scripts\python.exe" (
    echo 尚未安装环境，正在自动调用安装程序 ...
    echo.
    call "%~dp0installer.bat"
    if errorlevel 1 exit /b 1
)

echo 正在启动员工花名册统计系统 ...
start "" ".venv\Scripts\pythonw.exe" "%~dp0main.py"
if errorlevel 1 (
    echo [错误] 启动失败，请尝试手动运行 installer.bat 重新安装环境。
    pause
    exit /b 1
)
exit /b 0
