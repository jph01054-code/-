@echo off
setlocal
cd /d "%~dp0"
title SmartStore - GUI check
if not exist ".venv\Scripts\python.exe" (
  echo Run install.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m smartstore.launcher --check
set "TASK_CHECK_RESULT=%ERRORLEVEL%"
echo.
if "%TASK_CHECK_RESULT%"=="0" echo GUI construction passed.
if not "%TASK_CHECK_RESULT%"=="0" echo Check the error text above and startup-error.log in LOCALAPPDATA\SmartStoreAssistantV2.
pause
exit /b %TASK_CHECK_RESULT%
