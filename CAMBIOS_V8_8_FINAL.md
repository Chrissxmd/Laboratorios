# Cambios v8.8 final casi producción

Esta versión consolida los ajustes posteriores a la prueba de 30 PDFs.

## Seguridad de carga SAIRC

- `sairc_formulario2.csv` ahora contiene **solo registros cargables**.
- Se agregan CSV separados:
  - `sairc_cargable.csv`
  - `sairc_revision.csv`
  - `sairc_no_cargable.csv`
  - `sairc_todos_con_estado.csv`
- En Excel se mantienen hojas separadas:
  - `SAIRC_Cargable`
  - `SAIRC_Revision`
  - `SAIRC_No_Cargable`
  - `SAIRC_Formulario2` con todos los estados para auditoría.

## Identidad

- Se mantiene regla dura: si el documento del PDF no coincide con el documento del nombre del archivo, el registro queda como no cargable.
- Se separan columnas:
  - `requiere_verificacion_identidad`
  - `requiere_verificacion_resultados`
  - `requiere_verificacion_humana`

## Normalización mejorada

- Normalización Unicode/confusables para evitar fallas como `HEMOGLOΒΙΝΑ` con letras griegas.
- Nuevos alias:
  - `FOSFATA ALCALINA` -> `FOSFATASA_ALCALINA`
  - `BUN` -> `UREA_PRE`
  - `Hepatitis B Anti Core Total` -> `ANTI_HBC`
- `CALCIO IONICO` sigue excluido para no confundirlo con calcio total.

## Reporte

- Corrección del promedio de segundos por PDF en la hoja Resumen cuando se reconstruye desde costos/latencia.
- Mantiene reproceso desde caché IA sin volver a consumir Gemini.

## Recomendación de uso

Para reprocesar resultados sin volver a pagar Gemini:

```bat
python cli.py --modo reprocesar_ai --input "D:\RESULTADOS_SAIRC"
```

Para producción, usar preferentemente:

- `sairc_cargable.csv` para carga.
- `sairc_revision.csv` y `sairc_no_cargable.csv` para verificación humana.
- No usar `sairc_todos_con_estado.csv` como archivo de carga.
