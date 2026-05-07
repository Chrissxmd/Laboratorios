# CAMBIOS FRONTEND RESPONSIVE v8.8.3

## Mejoras aplicadas

1. **Corrección de superposición en ventana no maximizada**
   - La interfaz principal ahora usa un `QScrollArea`.
   - Si el ancho disponible no alcanza, el contenido ya no se monta unos sobre otros.
   - Se puede desplazar el contenido en vez de romper el layout.

2. **Panel de velocidad más estable**
   - Los controles avanzados fueron reorganizados en una cuadrícula de 2 columnas por 2 filas:
     - Hilos
     - RPM
     - Timeout
     - Reintentos
   - Esto evita que se superpongan cuando la ventana es más estrecha.

3. **Botón “Más información” funcional**
   - Se reemplazó el texto estático por un botón real.
   - Ahora abre una ventana explicando los perfiles:
     - Seguro
     - Recomendado
     - Rápido
     - Avanzado

4. **Ajustes de layout**
   - Se redujeron anchos mínimos de algunos paneles laterales.
   - Se ajustaron factores de expansión para mejorar el reparto del espacio.
   - El panel de log usa una altura mínima un poco menor para adaptarse mejor.

## Se mantiene
- Stepper dinámico.
- Pasos completados con check verde.
- Estados visuales del proceso.
- Barra de progreso con porcentaje.
- Edición manual de hilos/RPM/timeout/reintentos.
- Cambio automático a modo Avanzado si modificas esos valores.
