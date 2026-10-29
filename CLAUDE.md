# Sistema de Condonaciones — instrucciones para Claude

> Claude Code lee este archivo automáticamente al abrir el repositorio.
> Detalle completo en la carpeta `docs/` (leer el que aplique ANTES de cambiar código).
> Si dos documentos se contradicen, manda el más reciente: `docs/cambios_oct2026.md` > `docs/contexto_proyecto.md`.

## Quién soy y cómo trabajar conmigo
- Soy Ramses, **principiante en programación**. Explícame en español sencillo y en pasos cortos qué cambiaste y por qué.
- En funciones grandes o ambiguas, **pregúntame antes de programar** (dame opciones y marca la recomendada). Pídeme capturas o ejemplos reales si hacen falta.
- Dame ideas de cómo mejorar el contexto o la forma de pedir las cosas para obtener mejores resultados.
- Las validaciones son informativas (no detienen el proceso) salvo que se acuerde lo contrario.

## Cómo se publican los cambios
1. Trabaja en una **rama nueva** y abre un **Pull Request** hacia `main` con un resumen en español.
2. Yo reviso y le doy **Merge**; Streamlit Community Cloud publica `main` solo en 1–2 minutos.
3. Si hace falta SQL: entrégalo como archivo `.sql` en la carpeta `sql/` y dime que lo corra en Supabase → SQL Editor → Run.
4. Si cambian `requirements.txt` o los secretos, o aparece un ImportError justo después de publicar: Streamlit Cloud → **Reboot app**.

## Qué es la app
Streamlit (Python 3.11) + Supabase (PostgreSQL, plan gratis) para una terminal portuaria (Manzanillo):
- 📊 **Análisis**: cruza Tabulador Comercial + Archivo BI, aplica 9 reglas de condonación y genera un Excel de 63 columnas.
- 📋 **Historial NC**, 📖 **Reglas de Aplicación**, 🗂️ **Gestión NC** (asignar, dar seguimiento y concluir Notas de Crédito; asignación masiva desde Excel en ciclo).
- 🔀 **Transferencias**: cruza Archivo Recinto + Sistema N4 y genera un Excel para otra plataforma.
- 🔧 **Clasificador de Casos**: clasifica correos de clientes contra un catálogo de 120 motivos (sin IA externa); los usuarios sugieren y el admin aprueba.
- 👥 **Usuarios** (solo admin): usuarios, rotación, catálogos.

## Archivos
- `app.py` — toda la interfaz (más de 3,400 líneas; dividirla es una mejora pendiente).
- `app/database.py` — TODAS las funciones de Supabase (usa la service key desde `st.secrets`).
- `app/validaciones.py`, `app/calendario.py`, `app/reporte.py`, `app/config.py` — motor de Análisis.
- `app/asignacion_masiva.py` — reparto en ciclo de NC + machote Excel.
- `app/transferencias*.py` — módulo Transferencias.
- `app/clasificador.py` (motor) y `app/ui_clasificador.py` (pantallas) — Clasificador de Casos.
- `app/escena_qc.py` — grúa QC en pixel art del encabezado (sprite en base64 + CSS).

## Reglas técnicas que ya nos costaron errores
- Streamlit vuelve a ejecutar TODO el script en cada clic: usa caché (`st.cache_data`) e invalídala después de guardar; escribe en la BD solo dentro de botones; agrupa campos en `st.form`.
- Usa `width='stretch'`, no `use_container_width`.
- Lee las columnas de Excel por el TEXTO del encabezado (excepto el Excel de asignación masiva, que va por posición).
- Cada tabla nueva lleva RLS + política `service_role_<tabla> ... for all to service_role using (true) with check (true)`, y se crea con `if not exists`.
- Al agregar una pestaña, actualiza `tabs_disponibles` y los índices `IDX_*` juntos.
- No reutilices nombres de variables globales en bucles (el bug de `nc` guardó basura en Historial).
- Ante un fallo silencioso de `database.py`, muestra temporalmente el error real en pantalla antes de adivinar.
- Hora de México: `America/Mexico_City`.

## Sesión e inicio de sesión (actualizado 28 oct 2026)
- El token de sesión vive en una **cookie** del navegador (`cmsa_sid`), NO en la URL. Si hay un `?sid=` en la URL, se ignora y se borra.
- La cookie se escribe y se borra con `st.html("<script>…</script>", unsafe_allow_javascript=True)` y se lee con `st.context.cookies`.
- La sesión dura 5 días (`DIAS_MAX_SESION`) y hay un máximo de 3 sesiones por usuario.
- **Nunca** vuelvas a poner tokens, contraseñas o llaves en la URL ni en el repositorio (es público). Los secretos van solo en Streamlit Cloud → Settings → Secrets.

## Pendientes / ideas (en orden de prioridad)
1. Respaldo periódico de las tablas a Excel.
2. Bitácora de acciones importantes (quién reasignó, concluyó o borró).
3. Dividir `app.py` en archivos por módulo.
4. Tablero de métricas.
5. Seguir pidiendo cambios con capturas y ejemplos reales.
