@echo off
setlocal
cd /d "%~dp0"
title SmartStore - Starting
if not exist "smartstore\launcher.py" (
  echo This folder is incomplete or outdated.
  echo Extract the ENTIRE latest ZIP, then run start.bat from that folder.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo First launch: installing dependencies. Please wait.
  call install.bat --from-start
  if errorlevel 1 goto failed
)
echo Opening the program window...
".venv\Scripts\python.exe" -m smartstore.launcher
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Startup failed. Copy the error text above.
echo Also check: %LOCALAPPDATA%\SmartStoreAssistantV2\startup-error.log
pause
exit /b 1
