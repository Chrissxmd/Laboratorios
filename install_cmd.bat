@echo off
setlocal ENABLEDELAYEDEXPANSION
title Lab Extractor Python - Instalar

cd /d "%~dp0"

echo ==========================================
echo   LAB EXTRACTOR PYTHON - INSTALACION
echo ==========================================
echo.

where py >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No se encontro el lanzador py.
    echo Instala Python 3.11+ y vuelve a intentar.
    echo.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [INFO] Creando entorno virtual...
    py -3 -m venv .venv
    if errorlevel 1 goto :fail
) else (
    echo [INFO] El entorno virtual ya existe.
)

if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] No se encontro .venv\Scripts\activate.bat
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :fail

echo [INFO] Actualizando pip...
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :fail

echo [INFO] Instalando dependencias del proyecto...
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo [OK] Instalacion completada.
echo.
echo Siguiente paso:
echo   - Doble clic en run_cmd.bat para abrir la interfaz
echo   - O usa run_cli_cmd.bat para modo consola
echo.
pause
exit /b 0

:fail
echo.
echo [ERROR] La instalacion fallo.
echo Revisa el mensaje anterior.
echo.
pause
exit /b 1
