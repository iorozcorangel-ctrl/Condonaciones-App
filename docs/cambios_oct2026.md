# Cambios recientes — Sistema de Condonaciones (complemento de contexto_proyecto)

> Complementa `contexto_proyecto (1).md`. Leer ambos al continuar en un chat nuevo.

## Gestión NC → ➕ Asignar NC: lista separada por estado (18 oct 2026)
Debajo de "Todas las NCs asignadas" la lista va en 4 pestañas (con contador):
🔵 NC Pendientes (estatus contiene "PENDIENTE", no concluida) · 🟢 NC Asignadas / en proceso (abiertas con otro estatus) · ✅ NC Concluidas (concluida y no rechazada) · ⛔ NC Rechazadas / Inhabilitadas (estatus contiene "RECHAZ" o inhabilitada). El cuerpo de cada NC se movió a la función `_render_nc_asignada(nc)` (así `nc` ya no es variable global del bucle). El buscador filtra dentro de todas las pestañas.

## Asignación masiva de NC desde Excel (18 oct 2026)
- Ubicación: Gestión NC → ➕ Asignar NC → expander "📥 Asignación masiva desde Excel" (solo admin). Lógica pura en `app/asignacion_masiva.py`.
- Excel por POSICIÓN (decisión del usuario): A = Fecha NC, B = NC externo (obligatorio formato `NC-` + 4/5 dígitos, se normaliza), C = Persona (opcional; nombre completo o username, sin acentos/mayúsculas, acepta "@user"). Si la fila 1 es encabezado se omite. Plantilla descargable.
- Ciclo (round-robin) entre usuarios activos con `usuarios.en_rotacion = true`, ordenados por `usuarios.orden_rotacion` (0/NULL al final, luego por nombre). Se configura en 👥 Usuarios → "🔄 Rotación de asignación masiva" (tabla editable + "💾 Guardar rotación"); sirve para sacar a quien está de vacaciones.
- Regla confirmada: una NC con persona manual CUENTA COMO SU TURNO → se le suma un "crédito" y el ciclo se la salta la próxima vez que llegue a ella (ej. A,B,C: NC1→A, NC2 manual C, NC3→B, NC4→A (salta C), NC5→B). Manual a alguien fuera de rotación (pero activo) se permite sin crédito; inactivo/no encontrado = error.
- El ciclo continúa entre cargas: estado `{"siguiente_id", "creditos"}` en tabla `configuracion_app` (clave `rotacion_nc`), se guarda solo al confirmar.
- Validaciones por fila (las filas con error se omiten, las demás se crean): fecha inválida/vacía, NC vacía, formato inválido, NC ya existente en `nc_asignaciones` (normalizada), NC repetida en el mismo Excel, persona no encontrada / inactiva, sin personas en rotación. Al confirmar se vuelve a revisar duplicados.
- Flujo: subir (st.form) → "🔍 Previsualizar" (tabla con asignado, modo Ciclo/Manual, resultado + reparto por persona) → "✅ Confirmar y crear N NC" o Cancelar. Notificación: UNA por persona ("Se te asignaron N NC nuevas: ...") en vez de una por NC (`crear_nc_asignacion(..., notificar=False)`).
- SQL: `SQL_asignacion_masiva.sql` (columnas `en_rotacion`, `orden_rotacion` en `usuarios`; tabla `configuracion_app` con RLS + política service_role). `obtener_usuarios()` ahora usa `select("*")` para no tronar si faltan columnas.
- Funciones nuevas en `database.py`: `actualizar_rotacion_usuario`, `obtener_config_app`, `guardar_config_app`.
- Machote descargable ("📄 Descargar machote (Excel con instrucciones)", `plantilla_excel_bytes(usuarios)`): hoja 1 «Cargar NC» (encabezados naranjas, solo títulos, sin filas de ejemplo para no crear NC por accidente; col. A con formato fecha, col. C con lista desplegable de personas activas), hoja «Instrucciones» (pasos, reglas del ciclo, motivos de rechazo, ejemplo) y hoja «Personas» (activos y si están en rotación, generada al momento). El sistema solo lee la primera hoja.

## Análisis: cruce de contenedores Tabulador vs BI (20 oct 2026)
Regla confirmada ("el archivo más chico debe estar completo en el otro"), en `validar_archivos()` de `app/validaciones.py`:
- Mismos contenedores → normal.
- Cantidad distinta y el archivo chico está completo dentro del grande → ALERTA informativa (lista los que sobran y los totales de cada archivo) y se continúa SOLO con los que coinciden.
- Misma cantidad pero números distintos, o el chico trae alguno que no está en el grande → SE DETIENE, se limpian los archivos para volver a subirlos.
- Bug corregido: los errores de validación se mostraban con `st.error` y enseguida `st.rerun()` los borraba. Ahora se guardan en `st.session_state["errores_carga"]` y se muestran arriba de los uploaders hasta que se sube un archivo nuevo.

## Historial NC: fechas (20 oct 2026)
- La "Fecha" del Historial es el momento del análisis (cuando se pulsa Descargar Reporte), no la fecha de la NC.
- Bug corregido: se mostraba/filtraba con la fecha UTC (`fecha_creacion[:10]`), así que lo descargado después de las 6 p.m. salía con el día siguiente. Ahora se convierte a hora de México (`_fecha_mx`) en la vista y en los filtros "Analizada desde / hasta"; el detalle muestra fecha y hora.
- Nuevo: columna `historial_nc.fecha_solicitud_nc` (date) — SQL `SQL_historial_fecha_solicitud.sql`. `registrar_nc(..., fecha_solicitud_nc=)` la guarda (si la columna aún no existe, reintenta sin ella para no fallar). Se muestra "Solicitud NC dd/mm/aaaa"; registros viejos muestran "—". `obtener_historial()` ahora usa `select("*")`.
- (25 oct) Definiciones confirmadas por el usuario: **Fecha solicitud NC** = fecha en que el CLIENTE hizo su solicitud en la página correspondiente; **Fecha de análisis** = fecha en que el usuario hizo el análisis en la app. Son distintas.
- Registros anteriores al cambio mostraban "Solicitud NC —". Solución: respaldo en pantalla con `nc_asignaciones.fecha_solicitud` (mismo número de NC normalizado) y SQL `SQL_rellenar_fecha_solicitud_historial.sql` que rellena la columna de forma permanente (solo los vacíos). NC que nunca se dieron de alta en Gestión NC seguirán en "—".

## Análisis: horario de programación del previo OBLIGATORIO (27 oct 2026)
- Antes era opcional ("Ajuste de horario de previo"). Ahora, por cada contenedor con FechaSolitudPrevio en el BI, se contestan 2 preguntas Sí/No: «¿Previo con PROFEPA?» y «¿Se programó antes de las HH:00?» (la hora depende del día y de PROFEPA). No se puede iniciar el análisis si falta alguno (`previo_faltantes`, error con la lista de contenedores). No aplica en Condonación Manual Directa.
- Cortes confirmados: previo normal L-V antes de 16:00 y sábado antes de 12:00; PROFEPA L-V antes de 13:00, sábado sin horario; domingo nunca (se resuelve solo, sin preguntar). Antes → el conteo arranca ese día; después/día sin horario → arranca el siguiente día con horario (`resolver_inicio_previo`, lógica sin cambios).
- Verificado con los 4 ejemplos del usuario (3 días hábiles, sin PROFEPA): lunes 12:00 → último día jueves; lunes 16:00 → viernes; sábado 9:00 → miércoles; sábado 13:00 → jueves.

## Seguridad: sesión en cookie, ya no en la URL (28 oct 2026)
- Brecha reportada por el usuario: el token de sesión iba en la URL (`?sid=...`); quien recibía el link entraba sin contraseña desde otra computadora.
- Ahora (`app.py`): el token se guarda en una cookie del navegador `cmsa_sid` (path=/, SameSite=Strict, Secure, max-age = DIAS_MAX_SESION = 5 días), escrita con `st.html(<script>…</script>, unsafe_allow_javascript=True)` en el primer render después del login (bandera `_cookie_pendiente`). Al abrir/recargar se lee con `st.context.cookies` → `verificar_sesion` (bandera `_cookie_revisada`, una vez por sesión de Streamlit).
- Un `?sid=` en la URL se ignora y se borra (los links viejos ya no dan acceso). Al Salir o al vencer la sesión se borra la sesión en BD y la cookie (`_borrar_cookie` → script con max-age=0 en la pantalla de login).
- Esto REEMPLAZA lo que dice `contexto_proyecto.md` sobre "la sesión vive en la URL" y "las cookies no funcionaron" (eso era con `st.components.v1.html`, que corre en un iframe; `st.html` con `unsafe_allow_javascript=True` sí corre en la página principal).
- (29 oct) Corrección: en Streamlit Community Cloud el F5 sacaba al usuario. La nube filtra las cookies antes de que lleguen a Python, así que `st.context.cookies` llegaba vacío (en local sí funcionaba). Ahora, si viene vacío, el componente `_lector_cookie` (`st.components.v2`, JS que lee `document.cookie` y manda el token con `setStateValue`) lo lee en el navegador. `None` = el navegador aún no contesta (se muestra el login un instante); `''` = no hay cookie. `_cookie_revisada` se marca solo cuando ya hay respuesta. Probado con Playwright simulando la nube (cookies ocultas al servidor): login → F5 sigue dentro; otro navegador → login; Salir → cookie borrada.
- Recomendado una vez: `delete from sesiones;` en Supabase para invalidar tokens ya compartidos.
- Probado (Streamlit 1.66 + Playwright, BD simulada): login → recarga sigue dentro; otro navegador con el mismo link → pide login; link viejo `?sid=token` → pide login; Salir → cookie borrada y recarga pide login.
