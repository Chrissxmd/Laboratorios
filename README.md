# Lab Extractor Gemini/IA SAIRC — v8.8

Versión orientada a procesamiento masivo de resultados de laboratorio de pacientes con ERC en hemodiálisis.

## Cambios principales v8.8

1. **Control duro de identidad**
   - Extrae el documento desde el nombre del PDF.
   - Extrae el documento del paciente desde el contenido del PDF.
   - Si no coinciden: `NO_CARGABLE_IDENTIDAD` y requiere verificación humana.
   - El resultado se conserva para auditoría, pero no pasa a `SAIRC_Cargable`.

2. **Hojas nuevas en Excel**
   - `SAIRC_Cargable`: registros aptos para carga automática.
   - `SAIRC_Revision`: registros con validaciones críticas o datos incompletos.
   - `SAIRC_No_Cargable`: identidad no válida u otros bloqueos fuertes.
   - `Control_Identidad`: comparación documento archivo vs documento PDF.
   - `Resumen_IPRESS`: totales por carpeta/IPRESS.
   - `Alertas_Calidad`: alertas clínicas, unidades dudosas e inconsistencias.
   - `Costos_Latencia`: tiempos separados de carga PDF, IA, normalización y costo.

3. **Reglas ajustadas a hemodiálisis**
   - No bloquea automáticamente valores patológicos esperables en ERC/hemodiálisis.
   - Solo bloquea o manda a revisión crítica valores improbables, incoherentes o sospechosos de cruce de tabla.
   - Ejemplos: urea post >= urea pre, sodio incompatible, PRU ilógico, valores fisiológicamente improbables.

4. **Serologías mejoradas**
   - Prioriza interpretación textual: `NO REACTIVO`, `REACTIVO`, `NEGATIVO`, `POSITIVO`, `INDETERMINADO`.
   - Conserva índice numérico como trazabilidad, sin reemplazar la interpretación cuando existe.

5. **Mejoras de latencia**
   - `countTokens` desactivado por defecto.
   - Modelo por defecto CLI: `gemini-2.5-flash-lite`.
   - Configuración rápida sugerida: `--threads 4 --rpm 300 --timeout 180 --retries 3 --no-count-tokens`.
   - Gemini permite hasta 8 hilos en la GUI/CLI, según capacidad real de la API y del equipo.

## Uso rápido con interfaz gráfica

```bash
python main.py
```

Selecciona:
- carpeta de entrada con PDFs;
- carpeta de salida opcional;
- proveedor/modelo/API key;
- hilos y RPM.

## Uso recomendado por consola

```bash
python cli.py --modo pdf --input "D:\PDF_LABORATORIOS" --provider gemini --model gemini-2.5-flash-lite --threads 4 --rpm 300 --timeout 180 --retries 3 --no-count-tokens --resume-fast
```

Con carpeta de salida:

```bash
python cli.py --modo pdf --input "D:\PDF_LABORATORIOS" --output-dir "D:\RESULTADOS_SAIRC" --provider gemini --model gemini-2.5-flash-lite --threads 4 --rpm 300 --timeout 180 --retries 3 --no-count-tokens --resume-fast
```

## Reprocesar sin volver a llamar a Gemini

Sirve para regenerar el Excel con nuevas reglas SAIRC usando el `json_ai_raw` ya guardado.

```bash
python cli.py --modo reprocesar_ai --input "D:\RESULTADOS_SAIRC"
```

## Regla de producción más importante

```text
Si documento_en_pdf != documento_en_nombre_archivo:
    estado_identidad = NO_CARGABLE_IDENTIDAD
    puede_cargarse_sairc = NO
    requiere_verificacion_humana = SI
```

## Interpretación de hojas

- Usa `SAIRC_Cargable` para carga automática inicial.
- Usa `SAIRC_Revision` para revisión humana antes de decidir carga.
- Usa `SAIRC_No_Cargable` para errores de identidad o bloqueos fuertes.
- Usa `Control_Identidad` para auditar casos donde el documento no coincide o no fue detectado.

## Recomendación operativa

Antes de producción plena, corre nuevamente la prueba de 464 PDFs y revisa:

- cantidad en `SAIRC_Cargable`;
- cantidad en `SAIRC_No_Cargable`;
- casos `NO_CARGABLE_IDENTIDAD`;
- casos `REVISAR_SIN_DOCUMENTO_PDF`;
- tiempos promedio en `Costos_Latencia`;
- alertas de `Pendientes_Alta`.

## Nota v8.8 final

- `sairc_formulario2.csv` queda como archivo de compatibilidad, pero ahora contiene solo registros cargables.
- Para auditoría completa usar `sairc_todos_con_estado.csv`.
- Para revisión humana usar `sairc_revision.csv` y `sairc_no_cargable.csv`.
- Se agregó normalización Unicode para nombres de análisis con caracteres visualmente parecidos.
