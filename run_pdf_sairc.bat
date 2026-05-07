@echo off
cd /d "%~dp0"
echo ============================================
echo  Lab Extractor Gemini/IA SAIRC v8.9 PRODUCCION
echo  Identidad + cargable/no cargable + reproceso 503/red
echo ============================================
echo.
set /p INPUT_DIR=Carpeta con PDFs: 
set /p OUTPUT_DIR=Carpeta de salida opcional ^(Enter = automatico^): 
set /p API_KEY=API key Gemini/IA: 
if "%OUTPUT_DIR%"=="" (
  python cli.py --modo pdf --input "%INPUT_DIR%" --provider gemini --model gemini-2.5-flash-lite --api-key "%API_KEY%" --threads 4 --rpm 180 --timeout 180 --retries 3 --no-count-tokens --resume-fast
) else (
  python cli.py --modo pdf --input "%INPUT_DIR%" --output-dir "%OUTPUT_DIR%" --provider gemini --model gemini-2.5-flash-lite --api-key "%API_KEY%" --threads 4 --rpm 180 --timeout 180 --retries 3 --no-count-tokens --resume-fast
)
pause
