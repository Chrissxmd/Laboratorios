@echo off
setlocal ENABLEDELAYEDEXPANSION
title LabExtractorOCR - Build EXE

cd /d "%~dp0"

echo ==========================================
echo   LABEXTRACTOROCR - COMPILAR EXE
echo ==========================================
echo.

where py >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No se encontro el lanzador py.
    echo Instala Python para Windows y marca "Add Python to PATH".
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

echo [INFO] Actualizando pip...
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo [ERROR] Fallo actualizando pip.
    pause
    exit /b 1
)

echo [INFO] Instalando dependencias del proyecto...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo instalando requirements.txt
    pause
    exit /b 1
)

echo [INFO] Verificando PyInstaller...
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] Instalando PyInstaller...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] No se pudo instalar PyInstaller.
        pause
        exit /b 1
    )
)

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist LabExtractorOCR.spec del /f /q LabExtractorOCR.spec

echo [INFO] Iniciando compilacion...
python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name LabExtractorOCR ^
  --collect-all PyQt6 ^
  --hidden-import=fitz ^
  --hidden-import=pytesseract ^
  --hidden-import=PIL ^
  --hidden-import=PIL._tkinter_finder ^
  main.py

if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller fallo. Revisa el log mostrado arriba.
    echo [INFO] Si solo se genero el .spec, la compilacion no termino correctamente.
    pause
    exit /b 1
)

if exist "dist\LabExtractorOCR\LabExtractorOCR.exe" (
    echo.
    echo [OK] EXE generado correctamente:
    echo dist\LabExtractorOCR\LabExtractorOCR.exe
) else (
    echo.
    echo [ERROR] No se encontro el exe esperado.
    echo Revisa la carpeta dist y el log de PyInstaller.
)

echo.
pause
