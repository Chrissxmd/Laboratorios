# Cambios frontend final — v8.8

Esta entrega mantiene el motor de extracción, normalización SAIRC, control de identidad, caché y generación de resultados de la v8.8 final. Los cambios se concentran en la interfaz gráfica.

## Mejoras visuales y operativas

- Nuevo diseño híbrido: **asistente paso a paso + producción segura**.
- Panel lateral con 5 pasos claros:
  1. Seleccionar carpetas
  2. Configurar IA
  3. Modo de velocidad
  4. Procesar
  5. Revisar resultados
- Nueva tarjeta superior de **PRODUCCIÓN SEGURA**.
- Paneles principales más amplios y alineados para evitar cortes de texto.
- Selector de velocidad por perfiles:
  - Seguro
  - Recomendado
  - Rápido
  - Avanzado
- En los perfiles Seguro/Recomendado/Rápido se bloquean los campos avanzados para evitar errores operativos.
- El modo Avanzado habilita edición manual de:
  - Hilos
  - RPM
  - Timeout
  - Reintentos
- Panel de estado con tarjetas separadas:
  - Cargables
  - Revisión
  - No cargables
  - Errores
  - Total
- Botón **Abrir resultados** agregado en la barra inferior.
- Botones inferiores rediseñados:
  - Abrir resultados
  - Pausar
  - Detener
  - Procesar PDFs

## Notas importantes

- No se cambió el motor de IA ni la lógica SAIRC.
- No se cambió el control duro de identidad.
- `sairc_formulario2.csv` se mantiene como archivo solo cargable.
- El frontend está pensado para la prueba grande previa a producción.
