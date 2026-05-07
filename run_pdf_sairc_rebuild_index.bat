@echo off
cd /d "%~dp0"
set /p INPUT_DIR=Ingrese carpeta con PDFs: 
set /p OUTPUT_DIR=Ingrese carpeta de salida: 
set /p API_KEY=API key Gemini/IA: 
python cli.py --modo pdf --input "%INPUT_DIR%" --output-dir "%OUTPUT_DIR%" --provider gemini --model gemini-2.5-flash-lite --api-key "%API_KEY%" --threads 4 --rpm 180 --timeout 180 --retries 3 --no-count-tokens --rebuild-index --resume-fast
pause
