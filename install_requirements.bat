@echo off
setlocal ENABLEDELAYEDEXPANSION
title LabExtractorOCR - Instalar dependencias

cd /d "%~dp0"

where py >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No se encontro el lanzador py.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [INFO] Creando entorno virtual...
    py -3 -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] No se pudo activar el entorno virtual.
    pause
    exit /b 1
)

python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo [ERROR] Fallo actualizando pip.
    pause
    exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo instalando requirements.txt
    pause
    exit /b 1
)

echo.
echo [OK] Dependencias instaladas correctamente.
pause
