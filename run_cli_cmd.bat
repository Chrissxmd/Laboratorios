@echo off
setlocal
title Lab Extractor Python CLI

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] No existe el entorno virtual.
    echo Ejecuta primero install_cmd.bat
    echo.
    pause
    exit /b 1
)

echo ==========================================
echo   LAB EXTRACTOR PYTHON - CLI
echo ==========================================
echo.

".venv\Scripts\python.exe" cli.py %*
set EXITCODE=%ERRORLEVEL%

echo.
if not "%EXITCODE%"=="0" (
    echo [ERROR] El proceso termino con codigo %EXITCODE%.
    echo.
    pause
)
exit /b %EXITCODE%
