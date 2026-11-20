@echo off
chcp 65001 >nul
title 员工花名册统计系统 - 安装程序
cd /d "%~dp0"

echo ============================================
echo    员工花名册统计系统   环境安装
echo ============================================
echo.

echo [1/4] 检查 Python 环境 ...
where python >nul 2>&1
if errorlevel 1 (
    echo   [错误] 未找到 Python，请先安装 Python 3.9 及以上版本，
    echo           安装时务必勾选 "Add Python to PATH"。
    echo           下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo   %%v

echo.
echo [2/4] 创建独立虚拟环境 .venv ...
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 (
        echo   [错误] 虚拟环境创建失败。
        pause
        exit /b 1
    )
    echo   虚拟环境创建完成。
) else (
    echo   虚拟环境已存在，跳过。
)

echo.
echo [3/4] 升级 pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q

echo.
echo [4/4] 安装依赖（首次可能需要几分钟，请耐心等待） ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo   [错误] 依赖安装失败，请检查网络连接后重试。
    pause
    exit /b 1
)

echo.
echo ============================================
echo    安装完成！请双击运行 "启动软件.bat" 使用。
echo ============================================
pause
