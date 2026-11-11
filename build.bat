@echo off
setlocal
cd /d "%~dp0"
if exist dist\Feel rmdir /s /q dist\Feel
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean feel.spec
if errorlevel 1 exit /b 1
echo.
echo Build OK: %~dp0dist\Feel\Feel.exe
endlocal
