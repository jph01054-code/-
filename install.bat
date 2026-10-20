@echo off
setlocal
cd /d "%~dp0"
title SmartStore - Installation
set "TASK_PYTHON_CMD="
py -3 --version >nul 2>&1
if not errorlevel 1 set "TASK_PYTHON_CMD=py -3"
if not defined TASK_PYTHON_CMD (
  python --version >nul 2>&1
  if not errorlevel 1 set "TASK_PYTHON_CMD=python"
)
if not defined TASK_PYTHON_CMD goto missingpython
%TASK_PYTHON_CMD% -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if errorlevel 1 goto missingpython
if not exist ".venv\Scripts\python.exe" (
  %TASK_PYTHON_CMD% -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m smartstore.launcher --check
if errorlevel 1 (
  echo GUI check failed. Modify your Python installation to include Tcl/Tk, or run Repair.
  goto failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Google Chrome must be installed separately. The program uses your installed Chrome.
echo Installation completed. Run start.bat.
if /I not "%~1"=="--from-start" pause
exit /b 0
:missingpython
echo Install Python 3.11 or newer from python.org.
echo Include Tcl/Tk, Python Launcher, and Add Python to PATH.
pause
exit /b 1
:failed
echo.
echo Installation failed. Copy the error text above.
pause
exit /b 1
