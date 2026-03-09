@echo off

REM 检查是否安装了 Python
where python >nul 2>&1
if errorlevel 1 (
    echo Python 未安装或未添加到 PATH 中。
    exit /b 1
)

REM 检查 Python 是否为 Python 3
for /f "tokens=2 delims= " %%i in ('python --version 2^>^&1') do (
    set version=%%i
    goto check_version
)

:check_version
if not defined version (
    echo 无法检测 Python 版本。
    exit /b 1
)

for /f "tokens=1 delims=." %%j in ("%version%") do (
    if %%j LSS 3 (
        echo 检测到 Python 版本为 %version%，需要 Python 3。
        exit /b 1
    )
)

REM 调用 Python 脚本 repo.py，并传递所有参数
python "%~dp0repo.py" %*