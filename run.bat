@echo off
setlocal
set "FEEL_LAUNCH_DIR=%CD%"
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\pythonw.exe"
if exist "%PY%" goto :launch
set "PY=%~dp0.venv\Scripts\python.exe"
if exist "%PY%" goto :launch
echo [Feel] .venv not found. See README to create it.
pause
exit /b 1
:launch
start "" "%PY%" "%~dp0main.py" %*
