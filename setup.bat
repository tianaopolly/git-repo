@echo off
chcp 65001 >nul
setlocal

set "TARGET=%USERPROFILE%\bin"

REM 1) 若不存在则创建 %USERPROFILE%\bin
if not exist "%TARGET%" (
    mkdir "%TARGET%" || (
        echo 无法创建目录 "%TARGET%"，错误码 %ERRORLEVEL%.
        exit /b 1
    )
)

REM 3) 复制 repo 和 repo.cmd 到 %USERPROFILE%\bin
copy /Y "%~dp0repo.sh" "%TARGET%\repo" >nul 2>&1
copy /Y "%~dp0repo" "%TARGET%\repo.py" >nul 2>&1
copy /Y "%~dp0repo.cmd" "%TARGET%\" >nul 2>&1

REM 2) 将 %USERPROFILE%\bin 添加到当前用户环境变量 PATH（避免重复）
echo %PATH% | find /I "%%USERPROFILE%%\bin" >nul
if %ERRORLEVEL%==0 (
    echo "%%USERPROFILE%%\bin" 已存在于当前 PATH 中。
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$t = '%%USERPROFILE%%\bin';" ^
        "$p = [Environment]::GetEnvironmentVariable('Path','User');" ^
        "if ([string]::IsNullOrEmpty($p)) { [Environment]::SetEnvironmentVariable('Path',$t,'User') } else { $parts = $p.Split(';') | Where-Object { $_ -ne '' }; if ($parts -notcontains $t) { [Environment]::SetEnvironmentVariable('Path',( $p.TrimEnd(';') + ';' + $t ),'User') } }"

    REM 更新当前会话的 PATH（立即生效，仅对当前窗口）
    set "PATH=%PATH%;%%USERPROFILE%%\bin"
    echo 已将 "%%USERPROFILE%%\bin" 添加到当前用户 PATH（永久生效，需要重新登录或重开终端使系统级程序读取到新值）。
)

echo 完成repo安装。
endlocal

pause