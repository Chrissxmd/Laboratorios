# Lab Extractor Gemini/IA SAIRC v8.8

Versión basada en lectura directa de PDF con Gemini u otra IA multimodal, mejorada para generar Excel final compatible con flujo SAIRC.

## Importante

Esta versión **no genera JSON OCR tipo Azure**. Guarda una respuesta estructurada de la IA en `cache_ai/json_ai_raw`. Ese archivo sirve para auditoría y reproceso sin volver a pagar API, pero no contiene coordenadas OCR ni líneas/palabras como Azure Document Intelligence.

## Flujo

```text
PDF directo → Gemini/IA → json_ai_raw → normalización SAIRC → Excel final
```

## Salidas principales

En la carpeta de salida se generan:

```text
resultados_laboratorio_sairc.xlsx
resultados_normalizados.csv
sairc_formulario2.csv
pendientes_revision.csv
archivos.csv
manifest.json
process.log
process.jsonl
cache_ai/json_ai_raw/
cache_ai/json_ai_normalizado/
estado_pdf/
```

El Excel contiene:

```text
Resumen
Control_Calidad
Resultados_Normalizados
SAIRC_Formulario2
Archivos
Pendientes_Revision
Raw_Gemini
Costos
Errores
```

## Ejecutar PDF directo

```bat
python cli.py --modo pdf --input "D:\PDF_LABORATORIOS" --provider gemini --model gemini-2.5-flash --threads 1 --rpm 10 --timeout 120 --retries 4
```

Recomendado para primera corrida:

```bat
python cli.py --modo pdf --input "D:\PDF_LABORATORIOS" --provider gemini --model gemini-2.5-flash --threads 1 --rpm 6 --timeout 180 --retries 4 --resume-fast
```

## Reprocesar sin volver a llamar IA

Si ya tienes `cache_ai/json_ai_raw`, puedes regenerar Excel con nuevas reglas:

```bat
python cli.py --modo reprocesar_ai --input "D:\PDF_LABORATORIOS\salida_laboratorio_gemini_sairc_v8_8"
```

O directamente:

```bat
python cli.py --modo reprocesar_ai --input "D:\SALIDA\cache_ai\json_ai_raw" --output-dir "D:\SALIDA_REPROCESADA"
```

## Diferencias frente a Azure

| Punto | Azure OCR | Gemini/IA directa |
|---|---|---|
| Intermedio | JSON OCR técnico | JSON generado por IA |
| Coordenadas | Sí | No |
| Trazabilidad palabra/línea | Alta | Media |
| Interpretación de tablas complejas | Media/Alta | Alta, pero con riesgo generativo |
| Riesgo de alucinación | Bajo | Medio |
| Uso recomendado | Motor principal productivo | Alternativa/fallback o segunda lectura |

## Reglas de seguridad

- No se inventan resultados faltantes.
- Se marca `REVISAR` cuando hay valores fuera de rango plausible.
- Se calcula PRU solo si existen urea pre y urea post.
- Se separan pendientes en `Pendientes_Revision`.
- Se agrega `usar_en_sairc`: `SI`, `SI_CON_ALERTA`, `REVISAR` o `NO`.

## Recomendación operativa

Usar con producción controlada:

1. Procesar lote pequeño.
2. Revisar `Pendientes_Revision`.
3. Confirmar costo por PDF en hoja `Costos`.
4. Reprocesar cache si se ajustan reglas, sin llamar de nuevo a IA.


## Cache rápido v8.8

Esta versión agrega `cache_ai/cache_index.sqlite` para retomar lotes grandes sin validar todo el cache al inicio.

Parámetros útiles:

```bat
--resume-fast
--rebuild-index
--skip-cache-validation
```

`--resume-fast` está activo por defecto. Si se detiene un lote de 2,000 PDFs, vuelve a lanzar el mismo comando y el programa saltará los PDFs ya marcados como exitosos en el índice.

## Documento desde el nombre del PDF

La hoja `SAIRC_Formulario2` incluye la columna:

```text
documento_archivo_pdf
```

Ejemplo:

```text
04021826_REA_30032026_00008181.pdf -> 04021826
```

También se incluye `coincidencia_documento` para comparar ese documento con el documento leído por la IA dentro del PDF.


## Pausar, retomar y detener desde la GUI v8.8

La interfaz gráfica incluye botones **Pausar**, **Retomar** y **Detener**.

- **Pausar**: no corta la llamada API que ya está en curso; espera a que termine el PDF actual y evita iniciar nuevos PDFs.
- **Retomar**: continúa desde el siguiente PDF pendiente usando `cache_index.sqlite`.
- **Detener**: solicita la cancelación del lote. El PDF que ya fue enviado a la API puede terminar, pero el avance queda guardado en cache IA y en el índice SQLite. Al ejecutar nuevamente, el programa retoma desde lo avanzado.

Para lotes grandes, usar siempre `--resume-fast` o la GUI normal, que ya lo activa por defecto.
