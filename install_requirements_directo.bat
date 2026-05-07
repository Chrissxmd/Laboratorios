@echo off
cd /d "%~dp0"
echo Instalando dependencias en el Python actual...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
pause
