# Lab Extractor Gemini/IA SAIRC v8.9 Producción

## Objetivo de la versión

Esta versión endurece la estabilidad operativa para procesamiento masivo de PDFs de laboratorio, manteniendo la lógica SAIRC e identidad de la v8.8.

## Cambios principales

### 1. Reproceso automático de errores temporales

Cuando el proceso detecta errores temporales como:

- `http_503`
- `http_502`
- `http_504`
- `rate_limit_429`
- `timeout_408`
- `network_error`
- `ai_failed` temporal

el PDF no queda solo como error final. El sistema:

1. termina el primer barrido del lote;
2. identifica errores temporales;
3. espera un periodo de recuperación;
4. reintenta automáticamente al final del lote;
5. repite en modo más seguro si persiste el error.

### 2. Cola de reproceso

Se generan nuevos archivos:

- `retry_queue.json`
- `errores_reprocesables.csv`

Estos contienen únicamente archivos con errores temporales que pueden reprocesarse.

### 3. Reprocesar errores desde GUI

Se agregó el botón:

- `Reprocesar errores`

Este botón toma la carpeta de resultados y vuelve a intentar solo los PDFs pendientes por errores temporales.

### 4. Reprocesar errores desde BAT

Nuevo archivo:

- `run_reprocesar_errores.bat`

Solicita:

- carpeta original de PDFs;
- carpeta de resultados con `retry_queue.json`;
- API Key.

### 5. Nuevo modo CLI

Se agregó:

```bat
python cli.py --modo reprocesar_errores --input "D:\PDFS" --output-dir "D:\RESULTADOS" --provider gemini --model gemini-2.5-flash-lite --api-key "API_KEY"
```

### 6. Perfiles más conservadores

Para reducir errores 503 por alta demanda:

- Seguro: 2 hilos / 60 rpm
- Recomendado: 4 hilos / 180 rpm
- Rápido: 6 hilos / 300 rpm
- Avanzado: editable

### 7. Producción segura

Se mantiene:

- control duro de identidad;
- `sairc_formulario2.csv` solo con cargables;
- hojas y CSV separados;
- reglas adaptadas a hemodiálisis;
- frontend responsive v8.8.3.

## Importante

La versión no detiene indefinidamente el sistema si se cae internet. En su lugar:

1. reintenta cada PDF según configuración;
2. marca errores temporales como reprocesables;
3. hace reproceso automático al final del lote;
4. deja cola para reproceso manual si el problema persiste.
