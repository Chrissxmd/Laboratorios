@echo off
cd /d "%~dp0"
echo =================================================
echo  Lab Extractor Gemini/IA SAIRC v8.8 - Reprocesar
echo =================================================
echo.
set /p INPUT_DIR=Carpeta de salida o json_ai_raw: 
python cli.py --modo reprocesar_ai --input "%INPUT_DIR%"
pause
