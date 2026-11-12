@echo off
title Fix it with Scrum - server
cd /d "%~dp0"
echo Starting the AI and the game. This takes about 20 seconds...
echo.
:: -Debug adds the developer buttons (skip Sprints, start or reset Projects 2 and 3). Delete it for a real class.
powershell -NoProfile -ExecutionPolicy Bypass -File "tools\start_all.ps1" -Debug -Open
if errorlevel 1 (
  echo.
  echo Tailscale is not available on this PC, so starting for this PC only instead...
  echo.
  powershell -NoProfile -ExecutionPolicy Bypass -File "tools\start_all.ps1" -Local -Debug -Open
)
echo.
echo The servers keep running in the background. Use "Stop Fix it with Scrum.bat" to stop them.
pause
