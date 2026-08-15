@echo off
chcp 936 >nul
setlocal
title AI Manga Drama Studio - 管理脚本
cd /d "%~dp0"
set "HASARG=%~1"

if /i "%~1"=="start"   goto :start
if /i "%~1"=="stop"    goto :stop
if /i "%~1"=="restart" goto :restart
if /i "%~1"=="desktop" goto :desktop
if /i "%~1"=="status"  goto :status
if /i "%~1"=="logs"    goto :logs

:menu
cls
echo.
echo   ======================================
echo      AI Manga Drama Studio 管理脚本
echo   ======================================
echo.
echo     1) 启动     (start)
echo     2) 停止     (stop)
echo     3) 重启     (restart)
echo     4) 桌面端   (desktop)
echo     5) 状态     (status)
echo     6) 查看日志 (logs)
echo     0) 退出
echo.
set /p choice=  请选择:
if "%choice%"=="1" goto :start
if "%choice%"=="2" goto :stop
if "%choice%"=="3" goto :restart
if "%choice%"=="4" goto :desktop
if "%choice%"=="5" goto :status
if "%choice%"=="6" goto :logs
if /i "%choice%"=="start"   goto :start
if /i "%choice%"=="stop"    goto :stop
if /i "%choice%"=="restart" goto :restart
if /i "%choice%"=="desktop" goto :desktop
if /i "%choice%"=="status"  goto :status
if /i "%choice%"=="logs"    goto :logs
if "%choice%"=="0" goto :bye
if /i "%choice%"=="exit" goto :bye
if /i "%choice%"=="quit" goto :bye
echo   无效选项，请重新输入
pause
goto :menu

:start
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0studio.ps1" start
goto :done

:stop
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0studio.ps1" stop
goto :done

:restart
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0studio.ps1" restart
goto :done

:desktop
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0studio.ps1" desktop
goto :done

:status
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0studio.ps1" status
goto :done

:logs
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0studio.ps1" logs
goto :done

:done
echo.
pause
if defined HASARG goto :bye
goto :menu

:bye
echo 再见！
ping 127.0.0.1 -n 2 >nul
exit /b 0
