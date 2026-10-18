@echo off
setlocal
cd /d "%~dp0"
py -3 --version >nul 2>&1
if errorlevel 1 (
  echo Install Python 3.11 or newer with Tcl/Tk and Python Launcher.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  if errorlevel 1 exit /b 1
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m playwright install chromium
if errorlevel 1 goto failed
echo Installation completed. Run start.bat.
pause
exit /b 0
:failed
echo Installation failed. Check the error message above.
pause
exit /b 1
