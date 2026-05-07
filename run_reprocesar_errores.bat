@echo off
cd /d "%~dp0"
echo ============================================
echo  Reprocesar errores temporales v8.9
echo  Usa retry_queue.json / errores_reprocesables.csv
echo ============================================
echo.
set /p INPUT_DIR=Carpeta original con PDFs: 
set /p OUTPUT_DIR=Carpeta de resultados con retry_queue.json: 
set /p API_KEY=API key Gemini/IA: 
python cli.py --modo reprocesar_errores --input "%INPUT_DIR%" --output-dir "%OUTPUT_DIR%" --provider gemini --model gemini-2.5-flash-lite --api-key "%API_KEY%" --threads 2 --rpm 120 --timeout 180 --retries 3 --no-count-tokens
pause
