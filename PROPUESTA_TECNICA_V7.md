# Propuesta técnica v7

## Objetivo de la v7
Endurecer el proyecto para procesamiento por lotes largos, priorizando:
- tolerancia a `HTTP 429`
- continuidad del lote
- reanudación de ejecución
- trazabilidad por PDF
- validación más fuerte del JSON de salida

## Mejoras implementadas

### 1. Control global ante rate limit
- Se añadió un `GlobalRateLimiter` compartido.
- Cuando aparece `429`, se activa una **pausa global**.
- El tiempo de espera escala según la racha de 429.
- Se respeta `Retry-After` cuando el proveedor lo devuelve.

### 2. Reintentos inteligentes por tipo de error
- `429`: espera larga + cooldown global.
- `network_error` / `timeout_408`: reintento corto progresivo.
- `invalid_json`: reintento corto.
- `403`: queda clasificado como `forbidden_403`.

### 3. Validación y limpieza del JSON
- Se valida que la respuesta sea un objeto.
- `resultados` debe ser lista.
- Se descartan filas inválidas o vacías.
- Se bloquean nombres anómalos como `index`, `item`, `valor`, `resultado`.

### 4. Reanudación del procesamiento
La salida ahora se guarda en una carpeta estable:
- `salida_laboratorio_v7/`

Subcarpetas:
- `json_raw/`
- `textos_extraidos/`
- `estado_pdf/`

Si un PDF ya tiene estado `success` y su JSON existe, el sistema reutiliza ese resultado sin reprocesarlo.

### 5. Trazabilidad por archivo
Cada PDF genera un `.meta.json` con:
- estado
- tipo de error
- modo de extracción
- fecha de actualización
- filas detectadas

### 6. Texto extraído persistente
Se guarda el texto final en `textos_extraidos/`.
Esto permite revisar OCR y evita repetir trabajo al reprocesar.

### 7. Consolidación final robusta
Los CSV finales se reconstruyen a partir del estado y JSON guardado:
- `resultados_laboratorio.csv`
- `errores_laboratorio.csv`

## Cambios operativos

### Nueva salida recomendada
Usar la carpeta fija `salida_laboratorio_v7` permite:
- retomar pendientes
- auditar resultados por PDF
- volver a correr sin perder trabajo previo

### Nuevos parámetros CLI
- `--rpm`
- `--cooldown-429`

Ejemplo:
```bash
python cli.py --input "D:\PDFs" --provider gemini --model gemini-2.5-flash --enable-ocr --threads 1 --rpm 8 --cooldown-429 60
```

## Orden recomendado de testing
1. Probar lote pequeño de 20-30 PDFs.
2. Revisar `errores_laboratorio.csv` por `error_tipo`.
3. Verificar cuántos fueron reutilizados en una segunda corrida.
4. Ajustar `--rpm` si el proveedor sigue devolviendo 429.
5. Validar calidad de campos vacíos y análisis anómalos.

## Siguiente ronda sugerida después del testing
- score de calidad por PDF
- segunda pasada automática de errores recuperables
- exportación a XLSX
- panel GUI con métricas por tipo de error
- configuración persistente en archivo `.json`
