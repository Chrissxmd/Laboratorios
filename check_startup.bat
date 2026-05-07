@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] No existe .venv. Ejecuta install_cmd.bat primero.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m py_compile main.py core\ai.py core\pdf_utils.py core\processor.py ui\worker.py
if errorlevel 1 (
  echo [ERROR] Hay un error de sintaxis o import.
  pause
  exit /b 1
)
echo [OK] Verificacion basica completada.
pause
