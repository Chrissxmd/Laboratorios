# Manual rápido — v8.9 Producción

## Uso recomendado por GUI

1. Ejecuta `run_cmd.bat`.
2. Selecciona la carpeta de PDFs.
3. Selecciona la carpeta de salida.
4. Ingresa API Key.
5. Usa perfil `Recomendado` para producción normal.
6. Presiona `Procesar PDFs`.

## Si Gemini o internet fallan

La v8.9 intenta reprocesar automáticamente errores temporales al final del lote.

Además, genera:

- `retry_queue.json`
- `errores_reprocesables.csv`

Si todavía quedan pendientes, presiona en la GUI:

```text
Reprocesar errores
```

o usa:

```bat
run_reprocesar_errores.bat
```

## Archivos seguros para SAIRC

El archivo:

```text
sairc_formulario2.csv
```

contiene solo registros cargables.

Los registros con identidad dudosa o documento no detectado quedan fuera de la carga automática.
