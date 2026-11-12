@echo off
title Fix it with Scrum - stop
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "tools\stop_all.ps1"
echo.
echo Stopped.
pause
