@echo off
setlocal
cd /d "%~dp0"
if exist dist\Fell rmdir /s /q dist\Fell
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean fell.spec
if errorlevel 1 exit /b 1
echo.
echo Build OK: %~dp0dist\Fell\Fell.exe
endlocal
