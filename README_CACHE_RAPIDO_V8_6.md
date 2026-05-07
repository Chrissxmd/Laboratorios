# Cache rápido v8.8 - Gemini/IA SAIRC

Esta versión mantiene el motor de lectura directa de PDF con IA, pero agrega un índice SQLite para reanudar lotes grandes sin validar todo el cache al inicio.

## Archivo nuevo

```text
cache_ai/cache_index.sqlite
```

Guarda por PDF:

```text
ruta_relativa
filename
carpeta_origen
size_bytes
mtime_ns
cache_stem
json_ai_raw
json_ai_normalizado
estado_pdf/meta
status
provider
model
```

## Reanudar rápido

```bat
python cli.py --modo pdf --input "D:\PDF_LABORATORIOS" --provider gemini --model gemini-2.5-flash --resume-fast
```

`--resume-fast` está activo por defecto.

## Reconstruir índice

Usar si copiaste una salida/cache antiguo o si el índice se perdió:

```bat
python cli.py --modo pdf --input "D:\PDF_LABORATORIOS" --output-dir "D:\SALIDA" --rebuild-index --resume-fast
```

## Máxima velocidad

```bat
python cli.py --modo pdf --input "D:\PDF_LABORATORIOS" --resume-fast --skip-cache-validation
```

Usar `--skip-cache-validation` solo si no moviste ni editaste manualmente el cache.

## Nueva columna en SAIRC

El Excel `SAIRC_Formulario2` ahora incluye:

```text
documento_archivo_pdf
```

Ese campo se extrae del nombre del PDF, por ejemplo:

```text
04021826_REA_30032026_00008181.pdf -> 04021826
```

También se agrega:

```text
coincidencia_documento
```

Valores posibles: `SI`, `SI_NORMALIZADO`, `NO`, `SIN_DOC_ARCHIVO`, `SIN_DOC_OCR`, `NO_DETECTADO`.
