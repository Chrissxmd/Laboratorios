# CAMBIOS FRONTEND FIXES v8.8.1

## Correcciones aplicadas

1. **Stepper lateral dinámico**
   - El paso activo ya no queda fijo en “1. Seleccionar carpetas”.
   - Ahora cambia según la interacción del usuario y durante el procesamiento:
     - Paso 1: carpetas
     - Paso 2: configuración IA
     - Paso 3: velocidad
     - Paso 4: procesar
     - Paso 5: revisar resultados

2. **Controles manuales editables**
   - Hilos, RPM, Timeout y Reintentos quedan siempre editables.
   - Los perfiles Seguro / Recomendado / Rápido cargan valores sugeridos, pero no bloquean la edición manual.

3. **Modo Avanzado más robusto**
   - Si el usuario cambia manualmente Hilos, RPM, Timeout o Reintentos, el perfil cambia automáticamente a “Avanzado”.

4. **Mejora de eventos del selector de perfil**
   - Se reemplazó la lógica basada en clic simple por una actualización más robusta usando cambios de estado del radio button.

5. **Ayuda visual adicional**
   - Se añadió texto de ayuda aclarando que los perfiles solo cargan valores sugeridos y pueden ajustarse manualmente.

6. **Pequeños ajustes de UX**
   - El paso lateral se actualiza al seleccionar carpetas, validar conexión, cambiar velocidad, iniciar procesamiento y finalizar.
   - El archivo actual se muestra también cuando llega nombre sin contador.
