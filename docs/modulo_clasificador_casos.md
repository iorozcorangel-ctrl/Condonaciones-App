# Módulo "🔧 Clasificador de Casos" — IMPLEMENTADO (27 oct 2026)

Fuente: Excel `tipos_de_casos.xlsx` actualizado por Ramses (120 motivos, 18 áreas; columnas MOTIVO DE CASO / AREA / CUANDO APLICA, con descripciones enriquecidas). La información puede cambiar a futuro → el admin la actualiza desde la app (editar o importar Excel).
Todo vive dentro de la app (Streamlit + Supabase), sin IA ni servicios externos.

## Archivos
- `app/clasificador.py` — motor puro: normalizar, raíces (5 letras, sin plurales), índice con pesos (motivo y palabras clave 3, cuándo aplica 1.2, área 0.6) × rareza (idf); `clasificar()` → top 3 + nivel alta/media/baja + empate; `buscar()`; `extraer_palabras_clave()` (privacidad: quita correos, contenedores, RFC, números, ligas y nombres propios); `leer_excel_catalogo()` (encabezados por texto, en las primeras 10 filas, cualquier columna); `comparar_con_catalogo()`; `exportar_excel()`; mascota pixel art embebida en base64 (`MASCOTA_PNG_B64`).
- `app/ui_clasificador.py` — pantallas: `render_clasificador(usuario, es_admin)` y `avisos_inicio_sesion()`.
- `app/database.py` — `obtener_clasif_motivos`, `guardar_clasif_motivo`, `crear_clasif_sugerencia`, `obtener_clasif_sugerencias`, `resolver_clasif_sugerencia`, `obtener_clasif_sugerencias_sin_notificar`, `marcar_clasif_sugerencias_notificadas`.
- `app.py` — pestaña nueva en `tabs_disponibles` (IDX_CLASIF = 5; IDX_USUARIOS pasa a 6) y avisos al iniciar sesión.
- `SQL_clasificador_casos.sql` — tablas `clasif_motivos` y `clasif_sugerencias` (RLS + política service_role) y carga inicial de los 120 motivos (solo si la tabla está vacía). Incluye palabras clave iniciales propuestas para 25 motivos frecuentes (editables por el admin).

## Pantallas
- 🔍 **Clasificar**: pegar correo (st.form) → top 3 con área, cuándo aplica, "no confundir con", barra de coincidencia y palabras que coincidieron; aviso de confianza/empate. "✅ Es este motivo" NO cambia el catálogo: crea una sugerencia tipo "palabras" con las palabras útiles del correo para que el admin la apruebe. Buscador por palabras a la derecha.
- 📚 **Catálogo**: tabla filtrable por área/texto para todos; descargar en Excel (mismo formato que se importa). Admin: editar/agregar motivo (nombre único), dar de baja (activo=false, no se borra), importar Excel con vista previa (nuevos / con cambios / sin cambios / no vienen) y opción de dar de baja los que no vienen.
- 💡 **Sugerencias**: cualquier usuario sugiere motivo nuevo, corrección, palabras clave/diferenciador o baja (comentario obligatorio); ve "Mis sugerencias". Admin: pendientes con edición del texto antes de aprobar, Aprobar / Rechazar (motivo obligatorio). Avisos al iniciar sesión (admin: pendientes; usuario: aprobada/rechazada).

## Pendientes / notas
- Algunas descripciones del Excel traen notas internas (ej. en "Aclaracion de facturas": "Pendiente verificar como quedaria el criterio…") que se muestran tal cual a los usuarios; el admin puede limpiarlas en Catálogo.
- Probado con Streamlit 1.66 y una base simulada: clasificar, confirmar, enviar/validar sugerencias, aprobar, buscar, importar Excel. No probado contra Supabase real.

## Mejoras (28 oct 2026)
- Debajo de las 3 sugerencias hay 2 opciones más: **4. Otros** (deja el caso como «Otros», sin enviar nada) y **5. Sugerir otro tipo de caso distinto** (el usuario escribe por qué ninguna es correcta, obligatorio, y opcionalmente elige el tipo correcto). Se guarda como sugerencia tipo `reclasificar` con las palabras útiles del correo y lo que el sistema había sugerido; el admin elige el tipo correcto (obligatorio para aprobar) y las palabras se agregan a ese tipo de caso.
- Sensibilidad / correos con varias peticiones (`app/clasificador.py`):
  - Campo **Asunto** aparte: sus palabras pesan ×2; las 2 primeras oraciones ×1.5; el resto ×1 (la idea principal suele ir en el asunto o al inicio). La 1.ª opción se marca «⭐ idea principal».
  - `limpiar_correo()`: ignora el hilo citado (De:/From:/-----Mensaje original/El … escribió:), avisos de confidencialidad, "Enviado desde" y todo lo que sigue a la despedida (firma).
  - Frases de 2+ palabras en las palabras clave («no puedo entrar», «sesion bloqueada») suman +6 si aparecen completas.
  - `temas_del_correo()`: clasifica oración por oración y muestra «🧩 El correo también menciona…» con los otros temas claros (puntaje ≥ 12, sin empate) y la oración donde aparecen.
  - Más palabras de relleno ignoradas al extraer palabras clave (escribo, sale, saber, paso, mes, pasado…).
