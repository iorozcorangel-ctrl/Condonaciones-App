# Ideas de mejora a futuro — Sistema de Condonaciones

> Pendientes acordados con Ramses el 18/10/2026. Ordenados del más al menos prioritario.
> Ninguno está implementado todavía.

## 1. Respaldo periódico (prioridad ALTA)
Exportar las tablas de Supabase a Excel una vez por semana (botón de descarga para el admin o tarea programada).
**Por qué primero:** es lo más barato de hacer y protege todo lo demás. Supabase gratis se pausa tras 7 días sin uso y no hay respaldo propio; si se pierde la base, se pierde el historial de NC, transferencias y usuarios.

## 2. Bitácora de acciones importantes (prioridad ALTA)
Registrar quién reasignó, quién concluyó, quién inhabilitó y quién borró una NC (y cuándo). Solo eventos de negocio, no cada clic, para cuidar el espacio del plan gratuito.
**Por qué:** responde "¿qué pasó con esta NC?" y da respaldo ante dudas o reclamos. Hoy al eliminar una NC no queda rastro.

## 3. Dividir `app.py` en archivos por módulo (prioridad MEDIA)
Separar Análisis, Historial, Gestión NC, Transferencias y Usuarios en archivos propios. No cambia nada visible.
**Por qué antes del tablero:** `app.py` pasa de 3,000 líneas; cada cambio nuevo es más riesgoso (ej. el bug de la variable `nc` que guardaba basura en Historial). Conviene hacerlo antes de agregar módulos grandes.

## 4. Tablero de métricas (prioridad MEDIA)
NC por persona, por estatus, tiempos de cierre y montos condonados por mes, con gráficas.
**Por qué:** los datos ya existen, da mucha visibilidad al trabajo del área. Se deja después de 1–3 porque es "valor agregado", no protege contra pérdidas ni errores.

## 5. Forma de trabajo: pedir cambios con capturas y ejemplos reales (práctica continua)
No es una tarea de programación sino la manera de pedir cambios: capturas de pantalla, ejemplos reales y preguntas antes de programar. Es lo que mejor ha funcionado y evitó mucho retrabajo. Mantenerla siempre.
