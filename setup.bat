@echo off
chcp 65001 >nul 2>&1
title 临床研究数据看板 - 环境初始化

echo ====================================================
echo    临床研究数据看板 - 环境初始化
echo ====================================================
echo.

cd /d "%~dp0"

REM 检查系统 Python
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] 创建虚拟环境...
if exist "venv" (
    echo 虚拟环境已存在，跳过创建
) else (
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo 虚拟环境创建成功
)

echo.
echo [2/3] 安装依赖...
venv\Scripts\pip.exe install flask flask-cors openpyxl -i https://pypi.mirrors.ustc.edu.cn/simple/
if %ERRORLEVEL% neq 0 (
    echo [错误] 安装依赖失败
    pause
    exit /b 1
)

echo.
echo [3/3] 初始化数据库...
if exist "data\clinical.db" (
    echo 数据库已存在，跳过初始化
) else (
    if not exist "data" mkdir data
    venv\Scripts\python.exe -c "import database; database.init_db(); print('数据库初始化完成')"
)

echo.
echo ====================================================
echo    初始化完成！双击"启动看板.bat"即可运行
echo ====================================================
echo.
pause
