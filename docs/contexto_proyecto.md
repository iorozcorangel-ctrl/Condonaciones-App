# CONTEXTO DEL PROYECTO — Sistema de Condonaciones
## Terminal Portuaria Pacífico

> Documento de contexto para continuar el desarrollo en un chat nuevo.
> Pega este documento completo al inicio de la conversación nueva.

---

## 1. DESCRIPCIÓN GENERAL

Aplicación web en **Streamlit** (Python) + **Supabase** (PostgreSQL) que automatiza el análisis de condonaciones de gastos extra (almacenaje, conexiones, admon y control) para contenedores en una terminal portuaria, y además incluye un módulo de gestión/seguimiento de Notas de Crédito (NC) con asignación de responsables.

- **Repositorio GitHub:** `iorozcorangel-ctrl/Condonaciones-App` (público)
- **Hospedaje:** Streamlit Community Cloud
- **URL en producción:** `https://condonaciones-app-jyn8zcntteazrkrzw4frrl.streamlit.app`
- **Base de datos:** Supabase (proyecto `condonaciones-db`), plan gratuito
- **Nombre de la app (page_title, encabezados):** "Sistema de Condonaciones"

### Estructura de archivos del repositorio

```
Condonaciones-App/
├── app.py                       ← Archivo principal (toda la interfaz)
├── requirements.txt             ← pandas, openpyxl, streamlit, supabase
├── .streamlit/
│   ├── secrets.toml             ← SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY
│   └── config.toml              ← Tema visual (colores naranja)
└── app/
    ├── __init__.py
    ├── config.py                ← Colores, columnas BI/Tabulador, festivos oficiales México
    ├── perfiles.py               ← (legado, ya no se usa — perfiles ahora en Supabase)
    ├── calendario.py             ← Lógica de días hábiles, cálculo de desfases R3/R4/R5
    ├── validaciones.py           ← Motor de las 9 reglas de negocio, validación de archivos
    ├── reporte.py                ← Generador del Excel final (63 columnas)
    └── database.py               ← TODAS las funciones que hablan con Supabase
```

**IMPORTANTE:** Cuando se pide un cambio de código, siempre se debe:
1. Modificar el archivo localmente
2. Copiarlo a `/mnt/user-data/outputs/streamlit_app/...` con la misma ruta
3. Presentar el archivo al usuario
4. El usuario lo sube manualmente a GitHub (raíz o carpeta `app/` según corresponda) editando con el lápiz ✏️, Ctrl+A, pegar, Commit
5. Streamlit Cloud redepliega automáticamente en 1-2 minutos

El usuario **no es programador**, requiere instrucciones paso a paso muy explícitas para cada acción en GitHub/Supabase (dónde dar clic, qué botón, etc.).

---

## 2. STACK TÉCNICO Y CONVENCIONES

- Python 3.11, Streamlit (versión reciente — usar `width='stretch'` en vez de `use_container_width=True`, que está deprecado)
- Supabase Python client (`supabase-py`), usando siempre el **service_role key** (bypassa RLS)
- Todas las tablas de Supabase tienen RLS activado con política `service_role_*` que da acceso total al service_role
- Zona horaria: México (`America/Mexico_City`), función `hoy_mx()` en `app.py` para fecha/hora correctas
- Colores: naranja `#E65100` como color primario (antes era azul, se cambió), fondo gris claro `#F5F5F5`

### Patrón de caché (importante para rendimiento)
Streamlit **ejecuta el código de TODAS las pestañas en cada interacción**, no solo la visible. Para evitar sobrecargar Supabase:
- Existen wrappers `_cached_nc_asignaciones()`, `_cached_usuarios()`, `_cached_nc_motivos()`, `_cached_nc_estatus()` con `@st.cache_data(ttl=...)` en `app.py`
- Después de cualquier creación/edición/eliminación se debe llamar `invalidar_cache_nc()` para refrescar al instante
- El reporte final (`reporte_bytes`) se genera UNA SOLA VEZ por sesión y se guarda en `st.session_state`, para no regenerarlo en cada rerender mientras el usuario está en la pantalla de descarga
- Los formularios NUNCA deben escribir a la base de datos fuera de un botón explícito "Guardar" — nada de auto-guardado en cada tecleo

---

## 3. BASE DE DATOS — TABLAS EN SUPABASE

### `usuarios`
```sql
id, username, password_hash (SHA-256 con salt fijo), nombre_completo, rol ('admin'|'usuario'),
activo (bool), fecha_creacion, ultimo_perfil_id (FK a perfiles)
```
Usuario admin inicial: `admin` / `Admin2026!`

### `perfiles` (perfiles de condonación)
```sql
id, nombre, es_default (bool, solo 1 registro true — CUIDADO: se duplicó una vez, verificar
si vuelve a pasar), regla1_activa, regla2_activa, dias_previo (default 3), dias_ferromex (default 3),
dias_carretero (default 2), na_previo, na_ffcc, na_carretero (bool — si true, esa regla no se
calcula y se pone "NA" en el reporte), fecha_creacion
```

### `sesiones` (persistencia de login) — ✅ FUNCIONANDO
```sql
id, usuario_id, token (64 hex chars), username, expira_en (TIMESTAMP — expiración ABSOLUTA
fija de 2 días desde creación, NO se extiende con actividad), ultima_actividad (informativo,
columna que se agregó tarde con ALTER TABLE — CUIDADO: si falta esta columna, crear_sesion()
falla silenciosamente y el login no persiste. Ya está agregada y confirmada funcionando),
fecha_creacion
```
**Constantes en `database.py`:** `DIAS_MAX_SESION = 2`, `MAX_SESIONES = 3` (máx. sesiones simultáneas por usuario, elimina la más antigua si se supera).
**Mecanismo confirmado funcionando:** token se guarda en `st.query_params["sid"]` (URL). Al recargar, se lee de la URL y se valida contra Supabase (`verificar_sesion`), que también actualiza `ultima_actividad`. Verificación periódica de expiración cada 2 minutos (no en cada render) vía `_ultima_verif_sesion` en session_state, para no golpear Supabase en cada clic.
**Se intentó** además persistir con cookies de navegador + iframe JS para que la sesión se cierre al cerrar el navegador — **NO FUNCIONÓ** (los componentes de Streamlit corren en iframe aislado sin acceso a la ventana padre, `window.location` dentro del iframe muestra `about:srcdoc`) y se revirtió. Solo queda la persistencia por URL con expiración absoluta de 2 días — no hay forma confiable de detectar "cierre de navegador" en Streamlit sin un componente personalizado.
**Diagnóstico usado para resolver:** se agregaron temporalmente displays de `st.query_params`, `session_state["session_token"]` y `except Exception as e: return f"ERROR::{e}"` en `crear_sesion` para exponer el error real, que resultó ser la columna `ultima_actividad` faltante. Todo el código de diagnóstico ya fue removido del archivo final.

### `historial_nc` y `detalle_nc` (registro de NCs procesadas en Análisis)
```sql
historial_nc: id, numero_nc, usuario_id, usuario_nombre, fecha_creacion, total_contenedores, monto_total
detalle_nc: id, historial_nc_id (FK), numero_nc, contenedor, numero_factura, fecha_creacion
```
Se llena automáticamente al descargar el reporte Excel desde la pestaña Análisis. Sirve para detectar contenedores/facturas duplicados entre NCs.

### Módulo "Gestión NC" — tablas nuevas
```sql
nc_motivos: id, texto, activo, orden   -- 11 motivos iniciales cargados, editable solo por Admin
nc_estatus: id, texto, activo, orden, es_concluido (bool)  -- 9 estatus iniciales, editable solo Admin
             -- El último "NOTA DE CREDITO EMITIDA" tiene es_concluido=TRUE

nc_asignaciones: id, nc_externo, nc_interno, responsable_id, responsable_nombre,
    fecha_solicitud, fecha_creacion, fecha_actualizacion, motivo, estatus (default
    'PENDIENTE DE REVISAR'), contenedores (TEXT, separados por coma), comentarios,
    numero_nc_emitida, cliente, numero_factura, vinculada_a (FK a sí misma, "vincular NC
    anterior"), estado_visual ('nuevo'|'seguimiento'|'reasignado' — colores 🔵🟢🟡),
    inhabilitada (bool), motivo_inhabilitacion, concluida (bool), creado_por, fecha_cierre

nc_notificaciones: id, usuario_id, nc_id, mensaje, vista (bool), fecha_creacion
    -- Popup al iniciar sesión (una vez por login, no se repite en cada rerun)

nc_duplicados_revisados: id, nc_id, contenedor, revisado_por, fecha_creacion
    -- Registro discreto cuando el usuario confirma "No es duplicado" ante una alerta

borradores_previo: id, usuario_id, numero_nc, contenedor, previo_num, fecha_programacion,
    fecha_posicionamiento, fecha_actualizacion
    -- UNIQUE(usuario_id, numero_nc, contenedor, previo_num)
    -- Guarda el progreso de captura manual de fechas de previo (ver sección 6)
```

**Para agregar cualquier tabla/columna nueva:** siempre usar `CREATE TABLE IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` y recordar agregar `ALTER TABLE ... ENABLE ROW LEVEL SECURITY;` + `CREATE POLICY "service_role_X" ON tabla FOR ALL TO service_role USING (true) WITH CHECK (true);` — si no, Supabase Advisor marca alerta de seguridad (no rompe funcionalidad pero es buena práctica).

**LECCIÓN APRENDIDA:** Cuando algo fallaba silenciosamente (ej. `crear_sesion()` devolvía vacío), la causa fue una columna que "creíamos" haber agregado pero nunca se ejecutó el `ALTER TABLE` real (`ultima_actividad` faltaba en `sesiones`). Ante cualquier fallo silencioso de una función de `database.py`, agregar temporalmente `except Exception as e: return f"ERROR::{e}"` para exponer el error real en pantalla antes de seguir adivinando.

---

## 4. LAS 9 REGLAS DE NEGOCIO (motor en `app/validaciones.py` y `app/calendario.py`)

El conteo de días es siempre por **día calendario completo**, nunca por horas (excepto el ajuste opcional de horario de previo descrito abajo, que solo decide desde qué DÍA arranca el conteo).

1. **Regla 1** — Plazo 30 días naturales entre `TimeOut` (BI) y Fecha de Solicitud NC (usuario). Si se excede, alerta acumulada, el usuario decide continuar o cancelar. Desactivable por perfil (`regla1_activa`).
2. **Regla 2** — Primera programación dentro de los primeros 4 días naturales desde `TimeIn` (Día 1 = día de ingreso). Se valida con `FechaSolitudPrevio` O `Fecha de Liberacion` (basta que una cumpla). Desactivable por perfil (`regla2_activa`).
3. **Regla 3** — Posicionamiento de previo: plazo de **3 días hábiles** (Lun-Sáb, default configurable por perfil `dias_previo`) desde `FechaSolitudPrevio` hasta `FechaPosicionamiento`. Domingos, festivos oficiales y días marcados en calendario NO cuentan en el plazo, pero SÍ cuentan como desfase una vez que ya hay desfase. Si `FechaSolitudPrevio` vacío → 0 días (previo opcional, no se solicitó).
   - **Cancelación de previo (`FechaCancelacion`):** si el Agente Aduanal cancela el previo y no espera su posicionamiento, el desfase se calcula usando `FechaSolitudPrevio` + `FechaCancelacion` en vez de `FechaPosicionamiento`, por contenedor individual. Se muestra alerta al iniciar el análisis para validar esta información.
   - **Ajuste de horario de previo (opcional):** el BI no trae la hora en que se programó el previo. En la pantalla de Análisis, justo después de subir el Archivo BI, el usuario puede activarlo manualmente por contenedor e indicar si se programó dentro o después de la ventana de asignación (`resolver_inicio_previo()` en `calendario.py`). Ventanas: previo normal Lun-Vie hasta 16:59 y Sáb hasta 12:00 (domingo sin ventana); previo PROFEPA Lun-Vie hasta 12:59 (sábado y domingo sin ventana). Si se programó dentro de la ventana, el conteo arranca el mismo día; si fue después (o cae en día sin ventana), arranca el siguiente día con ventana. Si no se activa para un contenedor, la regla corre normal.
4. **Regla 4** — Carga a góndola FFCC: plazo de **3 días naturales** (default, configurable `dias_ferromex`) desde `FechaFerroMex` hasta `Fecha Gondola`. Sin excepciones de calendario (días naturales puros). Si campos vacíos, la regla no aplica (0).
5. **Regla 5** — Entrega carretero: plazo de **2 días hábiles** (default, configurable `dias_carretero`) desde `Fecha de programación de entrega` hasta `TimeOut`. Sábado NO cuenta en el plazo solo si programó Jueves o Viernes. Domingo nunca cuenta en el plazo (pero si ya hay desfase, sí cuenta). Alertas adicionales: Liner (si `Fecha de autorización de solicitud por La naviera` tiene valor) y reprogramaciones (si `No. Entregas >= 2`) — se muestran acumuladas al final, no una por una.
6. **Regla 6** — Suma total: `Total = Regla3 + Regla4 + Regla5`.
7. **Regla 7** — Monto a condonar por almacenaje: `costo_dia = Almacenaje SubTotal / Almacenaje Qty`; `dias_condonar = MIN(Total Desfase, Almacenaje Qty)`; `monto = costo_dia * dias_condonar`. Ecualizado para nunca condonar más de lo facturado.
8. **Regla 8** — Igual que Regla 7 pero para conexiones (`Suministro De Energía Qty/SubTotal`), solo contenedores refrigerados. Si no hay cobro → "No aplica".
9. **Regla 9** — Servicio de Administración y Control: se condona TODO o NADA. Se condona solo si se cobró (`Servicio de Administración y Control Qty > 0`) Y el desfase total cubre el 100% de `Almacenaje Qty`.

### Campos "No aplica" (NA) por perfil
Cada perfil tiene checkboxes `na_previo`, `na_ffcc`, `na_carretero`. Si están marcados, esa regla no se calcula (0 días) y el reporte Excel muestra "NA" en las columnas correspondientes (`Pasó de los X días...`, `Cuántos días de desfase...`).

### Condonación Manual Directa
Checkbox en Análisis que, al activarse, oculta el cálculo automático de Reglas 3/4/5 y permite capturar directamente días para Previo/Ferroviario/Carretero. Al menos uno debe ser > 0. Las Reglas 1 y 2 se siguen validando igual. Respeta el mismo tope de no condonar más que lo facturado. El ajuste de horario de previo (ver Regla 3) se omite en este modo, porque las reglas 3/4/5 no se calculan.

### Captura manual de previos múltiples (para contenedores con `No. Servicios >= 2`)
El BI solo guarda una fecha de previo/posicionamiento aunque haya varios servicios. Si se detecta `No. Servicios >= 2`, aparece una alerta preguntando si se quiere ajustar manualmente. Si sí: se muestran acordeones por contenedor (uno por uno, colapsables) donde se capturan N previos con selector de fecha tipo calendario (`st.date_input`), cada uno con botón de eliminar (excepto el Previo 1). El guardado es automático campo por campo en la tabla `borradores_previo` (solo si el valor cambió, para no golpear la BD en cada rerender). Al finalizar, se recalcula la Regla 3 sumando los desfases de cada previo individual.

---

## 5. REPORTE EXCEL FINAL (`app/reporte.py`)

63 columnas en una sola hoja, encabezado verde azulado (`HEADER_COLOR_REPORTE`), centrado, negritas. Última fila = "Total de Monto Procedente" (suma de columna Monto Total).

Columnas clave a recordar:
- Col 1: Contenedor | Col 2: Procedente/No Procede (MANUAL) | Col 3: Fecha Solicitud NC | Col 4: Fecha Revisión NC (automática, fecha de hoy)
- Col 5: Monto solicitado (Tabulador: `IMPORTE SIN IVA A CONDONAR`)
- Cols 8-39: pares fecha+día de la semana en celdas combinadas (TimeIn, Revalidado, Previo, Posicionamiento, Liberación, FerroMex, Góndola, Entrega, CMSA Entrega, TimeOut)
- Col 18: **"¿Cuántos Servicios Programados?"** → usa `No. Servicios` del BI (NO `No. Services Order`, son campos DIFERENTES — este fue un bug corregido)
- Col 40: Comentarios — speech dinámico generado automáticamente mencionando solo los conceptos que aplican (Previo/FFCC/Carretero) con sus días
- Cols 41-43: Tipo contenedor, Sobredimensionado (IsOOG), Peligrosa (IsHazardous) — estos 2 últimos se convierten `True/1→"SI"`, `False/0→"NO"`
- Col 61: N° cuenta bancaria (CLABE) — se fuerza formato TEXTO (`número_format = "@"`) para evitar notación científica (bug corregido, salía `1.29E+16`)
- Col 62: Motivo del rechazo (MANUAL) | Col 63: NC CLIENTE

**Consolidación de duplicados** (en `validaciones.py`, función `validar_archivos`):
- Si el Tabulador Comercial tiene el mismo contenedor repetido → se agrupa sumando `IMPORTE SIN IVA A CONDONAR` y concatenando `CONCEPTOS A CONDONAR` con coma.
- Si el Archivo BI tiene el mismo contenedor repetido (por múltiples facturas) → se agrupa sumando campos de cantidad/monto (Almacenaje, Energía, No Show, Admon, Remanejo) y concatenando `No. Factura` con coma.
- Se filtran automáticamente filas con contenedor vacío o que no cumplen el formato válido (elimina leyendas/totales al final del archivo).

**Validación de formato de contenedor:** 11 caracteres = 4 letras + 7 números (normalizado a mayúsculas, sin espacios). Se valida contra ambos archivos antes de cruzar.

**Validación calendario vs TimeIn:** al iniciar análisis, si hay días marcados en el calendario anteriores al `TimeIn` más antiguo del lote, se desmarcan automáticamente con alerta informativa.

---

## 6. INTERFAZ — PESTAÑAS (todas dentro de `app.py`, un solo archivo gigante)

1. **📊 Análisis** — Flujo principal: selector de perfil (con resumen informativo de reglas activas), datos de solicitud (NC de una lista estricta O checkbox "Capturar manualmente NC" — mutuamente excluyentes; **la captura manual debe tener formato `NC-` + consecutivo de 4 o 5 dígitos**, ej. `NC-2585`, `NC-10000`: se acepta minúsculas/espacios sobrantes y se normaliza a mayúsculas, pero el guion es obligatorio; `NC2585`, `2585` o `NC-123` se rechazan con mensaje al darle "Iniciar Análisis". La regla vive en `app/validaciones.py` (`validar_formato_nc`, constantes `NC_DIGITOS_MIN`/`NC_DIGITOS_MAX`; si algún día hacen falta 6 dígitos, solo se cambia `NC_DIGITOS_MAX`). La NC elegida de la lista NO se valida con este formato, para no bloquear NCs viejas ya asignadas en Gestión NC), condonación manual directa, carga de 2 archivos Excel, ajuste de horario de previo (opcional, ver Regla 3), calendario de días no hábiles (festivos oficiales México precargados + días especiales marcados por usuario), botones Iniciar Análisis / Nuevo Análisis. Flujo de pasos vía `st.session_state["paso"]`: `inicio → previo_alerta (si aplica) → previo_manual (si aplica) → confirmacion → ajuste (si el usuario no está de acuerdo con desfases) → reporte`.

2. **📋 Historial NC** — Lista de NCs generadas (desde Análisis), con búsqueda por NC/contenedor/factura, filtro por usuario y rango de fechas, paginación de 20 por página. Admin puede eliminar registros.

3. **📖 Reglas de Aplicación** — Puramente informativo, visible para todos, explica las 9 reglas con acordeones y emojis. Incluye la explicación de `FechaCancelacion` y del ajuste de horario de previo dentro del acordeón de Regla 3.

4. **🗂️ Gestión NC** — Pestaña única con **sub-tabs anidados** (`st.tabs` dentro de `st.tabs`) para no saturar el menú principal:
   - **➕ Asignar NC** (solo Admin): crear NC (número + responsable + fecha + checkbox vincular a una NC raíz con buscador), previene duplicados de `nc_externo` (comparación normalizada), lista todas las NC con reasignar/inhabilitar/eliminar (eliminar es permanente, con doble confirmación, y borra en cascada de todas las pestañas de Gestión NC; inhabilitar es reversible y no destructivo).
   - **📌 NC Asignadas**: formulario por NC (campos fijos bloqueados: fecha, NC externo, responsable; campos editables: NC Interno, Motivo (lista), Estatus (lista), Contenedores (pegar texto libre, se auto-detectan con regex `[A-Z]{3}U\d{7}`, máx 300), Comentarios). Campo "Número de NC emitida" **solo aparece si Estatus == "NOTA DE CREDITO EMITIDA"** exactamente. Al guardar (botón único, NADA se auto-guarda antes) se valida duplicidad de contenedores contra otras NCs (2 escenarios: NC vigente → puede marcarse como duplicada e inhabilitarse; NC concluida → solo alerta, no bloquea). Si el Estatus contiene "RECHAZADA" o es un estatus marcado `es_concluido` con NC emitida capturada, la NC se concluye automáticamente y se mueve a NC Concluidas. Excluye NCs inhabilitadas de esta vista (se muestran en NC Concluidas, solo lectura). Se registran `fecha_creacion` y `fecha_cierre` (esta última se estampa una sola vez, al momento de concluir).
   - **✅ NC Concluidas**: solo lectura para usuarios, Admin puede reabrir (regresa a NC Asignadas, limpia `fecha_cierre`). Debajo se muestran también las NC inhabilitadas, solo lectura.
   - **🗃️ NC Creadas**: tabla pública de solo lectura con buscador, para que cualquiera consulte el estatus sin poder modificar. Muestra fecha de creación y de cierre ("Pendiente" si aún no aplica), y el número de NC emitida o "Pendiente"/"Rechazada" según el estatus.

   **Jerarquía de vínculos entre NC:** cada NC puede vincularse a una NC "raíz" (columna `vinculada_a`), formando una jerarquía de 2 niveles (raíz → hijas, nunca nietas). La función "Fusión" permite indicar que una NC "más alta" (vigente) reemplaza a una "más baja" (histórica), aplanando la cadena si la NC más baja ya tenía sus propias vinculaciones, para que el historial completo quede bajo la NC vigente.

5. **👥 Usuarios** (solo Admin) — CRUD de usuarios, cambio de contraseña, activar/desactivar. Al final de esta pestaña también está la gestión de **Motivos** y **Estatus** de NC (agregar/editar/desactivar).

**Herencia de datos:** al generar el reporte en Análisis, se busca automáticamente si existe una NC Asignada con ese mismo `nc_externo` (comparación normalizada, mayúsculas sin espacios); si existe, se le copian `Cliente` y `Número de Factura` (solo dígitos) tomados del BI. Si NO existe, se crea un registro "huérfano" en `nc_asignaciones` para que el Admin lo gestione después.

---

## 7. BUGS CORREGIDOS RECIENTEMENTE (por si reaparecen patrones similares)

- **`IndexError: tuple index out of range`** en `nav[N]` — pasa cuando se agrega una pestaña nueva a la interfaz pero no se actualiza `tabs_disponibles` o los índices `IDX_*` en el mismo commit. Siempre verificar que el número de pestañas en la lista coincida con los índices usados.
- **`UnboundLocalError`** con `COL_BI` — nunca hacer `from app.config import COL_BI` dentro de una función si ya está importado globalmente arriba del archivo, genera conflicto de scope.
- **Auto-guardado no deseado** — cualquier escritura a Supabase debe estar SIEMPRE dentro de `if st.button(...)`, nunca en el cuerpo de un `with st.expander():` sin guardia, porque ese código corre en cada rerender aunque el expander esté colapsado.
- **Re-ejecución del paso "reporte"** — cualquier paso de `st.session_state["paso"]` que haga trabajo pesado (generar Excel, crear registros en BD) debe protegerse con una bandera tipo `if not st.session_state.get("reporte_bytes"):` para que no se repita en cada clic mientras el usuario sigue en esa pantalla.
- **Streamlit reruns totales**: cualquier `obtener_*()` que se llame en varias pestañas debe cachearse (`@st.cache_data(ttl=...)`) e invalidarse manualmente tras mutaciones.
- **`st.components.v1.html` corre en iframe aislado** — nunca usarlo para intentar modificar `window.parent.location` o compartir cookies con la página principal, no tiene permisos para eso. Si se necesita mostrar HTML/CSS con estilo, usar `st.markdown(..., unsafe_allow_html=True)` en su lugar (no genera iframe).
- **`use_container_width` deprecado** — usar `width='stretch'` (True) o `width='content'` (False).
- **Fechas con notación científica en Excel** (CLABE) — forzar `number_format = "@"` (texto) en la celda.
- **Streamlit NO detecta headers reales (`st.header`, `st.subheader`, `st.title`, markdown con `#`) y les genera anchors automáticos que modifican el hash de la URL** — puede interferir con lógicas basadas en `st.query_params`. Evitar headers genuinos de Streamlit en pantallas donde la URL debe mantenerse limpia (usar `st.markdown` con HTML plano tipo `<div>` en su lugar, NO usar `<h1>`-`<h6>` tampoco para estar seguros).
- **Fallos silenciosos de Supabase** — cualquier función de `database.py` con `except Exception: return None/""` puede estar ocultando un error real (columna faltante, tabla faltante, etc.). Ante comportamiento raro sin mensaje de error, exponer temporalmente el error real con `except Exception as e: return f"ERROR::{e}"` y mostrarlo en pantalla para diagnosticar, luego revertir a silencioso.
- **`st.stop()` detiene TODO el render de la página**, no solo la rama actual — usarlo dentro de un bloque de error corta la ejecución de todo lo que viene después en el script (incluyendo listas/tablas que se muestran más abajo). Preferir restructurar con if/elif/else en vez de `st.stop()` cuando hay contenido después que sí debe seguir mostrándose.
- **`st.tabs()` pierde la pestaña activa entre reruns** en versiones viejas de Streamlit — corregido fijando `streamlit>=1.56.0` en `requirements.txt`. Además, evitar renderizar elementos condicionales (banners, alertas) justo ANTES de la llamada a `st.tabs()`, porque su aparición/desaparición entre reruns puede resetear la pestaña activa igualmente — usar `st.toast()` (flotante) en vez de `st.info()`/contenedor fijo para notificaciones que aparecen antes de las pestañas.
- **`StreamlitDuplicateElementKey`** — ocurre cuando dos widgets dentro de un mismo loop terminan con la misma `key=`. Al construir keys dentro de loops sobre datos que pueden repetirse (mismo contenedor en 2+ registros), incluir SIEMPRE todos los identificadores relevantes en la key (no solo el id del registro actual, también el id del registro relacionado si aplica).
- **Pantalla se pone gris ("cargando") en cada interacción** — es el rerender completo que Streamlit hace ante CUALQUIER cambio de widget (escribir en un campo, subir un archivo, etc.), no un autoguardado real a la base de datos. Cuando una pantalla tiene varios campos/archivos que el usuario llena antes de un botón de acción, agruparlos dentro de `st.form("nombre_form")` con `st.form_submit_button(...)` en vez de `st.button(...)` evita el rerender hasta que se manda el formulario. Costo: dentro de un `st.form` no se permiten `st.button()` normales (solo el submit), y el botón de submit no se puede deshabilitar dinámicamente según otros campos del formulario (sus valores no son visibles hasta que se manda) — la validación de campos faltantes debe hacerse DESPUÉS de mandar el formulario, mostrando `st.error()` en vez de deshabilitar el botón de antemano. Aplicado en "🔀 Transferencias → 📤 Generar Transferencia".

---

## 8. LIMITANTES CONOCIDAS DEL PROYECTO (para mencionar si se pregunta)

- Streamlit Cloud (gratis): la app puede dormir tras inactividad, tarda unos segundos en despertar
- **Reboot manual tras subir varios archivos nuevos a la vez:** al agregar varios archivos nuevos en un mismo commit (por ejemplo, al implementar el módulo Transferencias: `app.py` + `database.py` + 3 archivos nuevos), Streamlit Cloud a veces se queda con la versión vieja en memoria y marca `ImportError` aunque el código en GitHub ya esté correcto y completo (verificado byte a byte). La solución es entrar a share.streamlit.io → menú de tres puntos junto al nombre de la app → **"Reboot app"**, esperar 1-2 minutos. Antes de sospechar de un error real en el código, vale la pena probar el reboot manual primero cuando el error aparece justo después de subir varios archivos juntos.
- Supabase (gratis): el proyecto se pausa tras 7 días sin actividad, hay que entrar a Supabase periódicamente para reactivarlo (toma minutos a veces horas)
- Sesión persiste máx. 2 días vía URL con token — NO se puede garantizar cierre de sesión al cerrar navegador (limitación de Streamlit, no hay forma confiable sin componente personalizado)
- Contraseñas con hash SHA-256 simple + salt fijo (no bcrypt) — suficiente para proyecto escolar, no para producción real
- Sin pruebas automatizadas
- Perfiles y usuarios ahora sí persisten en Supabase (ya no se pierden si Streamlit se reinicia)

---

## 9. MEJORAS FUTURAS SUGERIDAS (mencionadas en conversación, no implementadas)

- Dashboard de métricas con gráficas (montos condonados por periodo/usuario/servicio)
- Notificaciones por correo electrónico al generar NC
- Migración a FastAPI + React para interfaz más profesional
- Pruebas automatizadas de las reglas de negocio
- API REST para exponer las reglas a otros sistemas
- Exportar historial completo a Excel
- Bitácora/auditoría de acciones (se discutió, no implementado — preocupación por límite de almacenamiento del plan gratuito de Supabase; se sugirió registrar solo eventos de negocio importantes, no cada clic)

---

## 10. ESTILO DE TRABAJO CON EL USUARIO

- El usuario **no programa**, requiere instrucciones exactas paso a paso para GitHub (qué archivo, dónde el lápiz ✏️, Ctrl+A, pegar, Commit) y Supabase (SQL Editor, nueva consulta, Run)
- Prefiere que cada cambio se explique brevemente en español, sin tecnicismos innecesarios
- Le gusta que se le den opciones/sugerencias cuando algo es ambiguo, y a veces pide mockups visuales antes de programar (usar la herramienta de Visualizer para esto)
- Cuando pide una funcionalidad grande y compleja, es buena práctica confirmar el flujo completo con preguntas antes de programar (como se hizo con el módulo de Gestión NC, y como se está haciendo ahora con el módulo de Transferencias — ver sección 12)
- Todos los campos que vienen de archivos Excel deben leerse por el TEXTO del encabezado (nombre de columna), nunca por posición fija — los archivos de origen pueden traer las columnas en cualquier orden, y algunos (los que llena una persona a mano) tienen alta variabilidad en cómo se escribe el encabezado
- Ya se le recomendó migrar a un chat nuevo cuando la conversación se vuelve muy larga, para conservar rendimiento del modelo

---

## 11. CÓMO CONTINUAR

Si el usuario sube este documento a un chat nuevo, pedirle que también adjunte (o confirme que tiene disponibles) los archivos actuales del repositorio si se necesita ver el código exacto — este documento resume el QUÉ y el POR QUÉ, pero no contiene el código línea por línea. Para cambios puntuales, pedir al usuario que comparta el archivo específico a modificar (`app.py`, `app/database.py`, etc.) descargándolo de GitHub, o trabajar asumiendo la estructura aquí descrita y generar el archivo completo actualizado si es necesario.

---

## 12. NUEVO MÓDULO EN DISEÑO — "TRANSFERENCIAS" (EN DEFINICIÓN, AÚN SIN CÓDIGO)

Módulo nuevo, independiente del de Condonaciones (proceso distinto, datos distintos), pero vive **dentro de la misma app** (comparte login y usuarios — decisión ya confirmada con el usuario). Sigue el mismo patrón general que Condonaciones: se suben 2 documentos que se cruzan entre sí por campos clave, el sistema genera automáticamente un documento final (Excel descargable), y cada caso además queda **guardado como registro/bitácora simple** (folio + responsable informativo, SIN el flujo de estados que sí tiene NC — ver subsección dedicada más abajo).

**Estado actual: ESPECIFICACIÓN COMPLETA.** Ya se recopiló toda la información necesaria con el usuario (ver checklist al final de esta sección). El siguiente paso es el diseño técnico y la programación.

### Documento final (plantilla ya confirmada con el usuario)
- Se descarga como archivo Excel.
- La columna **A siempre debe quedar vacía** (el archivo resultante se sube después a otra plataforma externa que da error si la columna A tiene contenido). Mostrarla más angosta al generarse.
- Los datos arrancan en la columna **B**, con estas columnas en este orden:
  1. Id Solicitante — CÓDIGO numérico de la naviera (ver tabla de equivalencias Naviera → Código, en la subsección del Archivo Sistema N4). Sale del campo `Line Op` de ese archivo.
  2. No Contenedor
  3. Linea Op — el NOMBRE de la naviera tal cual (ej. "ONE"), sin convertir a código — sale del mismo campo `Line Op` del Archivo Sistema N4, pero en texto plano (distinto de "Id Solicitante", que sí lleva el código).
  4. Type Arch ISO
  5. Recinto Origen
  6. Recinto Destino
  7. Id Estado Contenedor — valor siempre fijo `1` (nunca `0` en este proceso, aunque el campo en teoría admite ambos)
  8. Trucking — valor siempre fijo, el texto literal `TC-TAE121220E95-01`, sin importar el contenedor o la solicitud

### Archivo de entrada 1 — "Archivo Recinto" (lo llena manualmente otra área, alta variabilidad de formato)
Especificación de campos del Excel origen (deben leerse por el TEXTO del encabezado, nunca por posición de columna, porque el orden varía entre archivos — y al ser llenado a mano, el texto exacto del encabezado también puede variar, contemplar alias reconocidos):

| Campo del archivo origen | Uso en el módulo |
|---|---|
| CATEGORIA | Necesario solo para **filtrar**, NO va al documento final. Dos valores posibles: `TRANSBORDO` (se conserva y procesa) e `IMPORTACIÓN` (se descarta, no se guarda). Mostrar alerta en pantalla con el total de cada uno al procesar, ej. "Total X Transbordos, Total X Importaciones (eliminadas)". |
| # | Informativo, no se usa |
| CONTENEDOR | **Necesario — va al documento final** (campo "No Contenedor") y además es el campo usado para **cruzar contra el Archivo Sistema N4** (ver validación de cruce más abajo). Alta variabilidad. Formato esperado: 11 caracteres totales — 4 letras (la 4ta letra siempre es "U") + 7 números. Quitar espacios al normalizar. Si el formato es inválido (ej. una letra de más) → NO intentar corregir solo, mandar alerta pidiendo corregir el archivo de origen. |
| LINEA NAVIERA | Informativo — se usa solo como dato de validación de referencia (se cruza contra `Line Op` del Archivo Sistema N4, ver abajo), pero **nunca debe detener el proceso** |
| SELLOS1 / SELLOS2 / SELLOS3 / SELLOS4 | Informativo, no se usan |
| IMPORTADOR // CONSIGNATARIO | Informativo, no se usa |
| MERCANCIA | Informativo, no se usa |
| REEFER | Informativo, no se usa |
| RECINTO ORIGEN | **Necesario — va al documento final** (campo "Recinto Origen"). No se usa el nombre tal cual: se traduce a un CÓDIGO numérico fijo usando la tabla de equivalencias de la subsección siguiente. |
| RECINTO DESTINO | **Necesario**, mismo caso que Recinto Origen (campo "Recinto Destino") — usa la MISMA tabla de equivalencias (los códigos aplican igual para origen que para destino, no son excluyentes entre sí). |
| STATUS 112-902/111 | Informativo, no se usa |
| FECHA/HORARIO | Informativo, no se usa |

#### Tabla de equivalencias — Recinto Origen / Recinto Destino (confirmada con el usuario)
En el Archivo Recinto, `RECINTO ORIGEN` y `RECINTO DESTINO` traen el NOMBRE del recinto (con alta variabilidad de escritura: mayúsculas/minúsculas, con/sin espacio, con/sin acento, con/sin espacio final). Para el documento final se debe convertir ese nombre al CÓDIGO numérico correspondiente — nunca se usa el nombre en el archivo final, solo el código:

| Nombre en Archivo Recinto (tal como puede venir escrito) | Código a usar en el documento final |
|---|---|
| API | 85 |
| LA JUNTA | 6383 |
| OCUPA | 4747 |
| SSA | 6381 |
| SSA MEXICO | 6381 |
| SSA MÉXICO | 6381 |
| SSAMEXICO | 6381 |
| SSAMÉXICO | 6381 |
| TIMSA | 6382 |
| CEMEX | 160 |
| CORPORACION | 154 |
| CONTECON | 480 |
| CONTECON (con espacio al final) | 480 |
| FRIMAN | 6 |
| HAZESA | 2164 |

**Nota de implementación:** varios nombres distintos mapean al mismo código (ej. SSA/SSA MEXICO/SSA MÉXICO/SSAMEXICO/SSAMÉXICO → 6381), así que la comparación debe normalizarse antes de buscar en la tabla: mayúsculas, sin espacios extra (incluyendo al final), y sin distinguir acentos (México = Mexico). Igual que con el contenedor, esta tabla de alias debe vivir centralizada en un solo lugar del código (como `COL_BI`/`COL_TAB` en `config.py`), no repetida en varios sitios.

**Recinto no reconocido — flujo confirmado con el usuario (catálogo editable con aprobación):**
Si un nombre de recinto no hace match con ningún alias conocido, NO se trata como un simple error de una sola vez — se resuelve dentro del propio sistema, sin necesitar retrabajo de código después:

1. Existe una tabla de recintos y códigos, visible para el usuario, de **solo lectura** — los CÓDIGOS nunca se pueden crear ni editar desde la interfaz (los 15 nombres/códigos de arriba son la base inicial, pero solo se agregan NOMBRES nuevos, nunca códigos nuevos).
2. Cuando el sistema encuentra un nombre de recinto que no reconoce, el usuario puede **proponer ese nombre nuevo y relacionarlo con uno de los códigos YA EXISTENTES** en la tabla (nunca inventa un código).
3. La fila que originó la propuesta se procesa de inmediato con el código elegido por el usuario — **no se detiene ni se bloquea** esperando aprobación.
4. Al proponerse, se envía una notificación a los usuarios Admin (reutilizando el mismo mecanismo que ya existe para `nc_notificaciones` en Condonaciones) para que autoricen agregar ese nombre nuevo de forma permanente al catálogo.
5. Una vez que un Admin aprueba, ese nombre queda guardado como alias reconocido de ese código, y los siguientes archivos que traigan ese mismo nombre lo detectan solos automáticamente, sin volver a preguntar.
6. **Cualquier usuario del módulo** puede proponer un nombre nuevo (no está restringido a Admin) — el control de calidad recae en que un Admin apruebe, no en restringir quién propone.

Esto extiende el patrón de "catálogo editable" que ya existe para Motivos/Estatus de NC en Condonaciones (ahí solo Admin edita directamente), agregándole un paso de propuesta-y-aprobación que ese catálogo no tiene. **Este flujo de propuesta+aprobación aplica SOLO al catálogo de Recintos** (porque ese archivo lo llena una persona a mano, con errores de dedo esperables) — el catálogo de Navieras (ver abajo) usa un flujo distinto, más simple.

### Archivo de entrada 2 — "Archivo Sistema N4"
**Estructura del Excel — CONFIRMADO:** este archivo trae 4 filas de encabezado del reporte (título, filtros aplicados, etc.) ANTES de los nombres de columna reales. Los nombres de columna (`Unit Nbr`, `Line Op`, etc.) están en la **fila 5** del Excel, y los datos de contenedores arrancan en la **fila 6**. El código ya lo contempla (`pd.read_excel(..., header=4)` — pandas usa índice base 0, así que la fila 5 humana es `header=4`; la constante vive en `app/transferencias_config.py` como `N4_FILA_ENCABEZADO`). El Archivo Recinto, en cambio, SÍ tiene sus encabezados normales desde la fila 1 — este ajuste de fila aplica solo al Archivo Sistema N4.

Tiene muchas columnas, pero solo se usan las siguientes (igual, leer por texto de encabezado, nunca por posición):

| Campo del archivo origen | Uso en el módulo |
|---|---|
| O/B Dclrd Mode | Modo de salida declarado del contenedor. Solo debe traer `Vessel` o `Truck`. Se valida cruzando contra `T-State` (ver regla de consistencia abajo). |
| Unit Nbr | Número de contenedor. Mismo formato que en Archivo Recinto: 11 caracteres, 4 letras + 7 números. **Confirmado como el campo de cruce contra el Archivo Recinto** (contra el campo `CONTENEDOR` de ese archivo — ver validación de cruce más abajo). |
| T-State | Estado actual del contenedor. Solo 2 valores posibles: `Inbound` o `Yard`. Debe ser consistente con `O/B Dclrd Mode`; si no concuerda, mostrar alerta (en NINGÚN caso detiene el proceso):<br>• `Inbound` + modo de salida `Truck` → inconsistente. Alerta: "Inbound - Truck: un contenedor de transferencia que no está ingresado a terminal no puede tener modalidad de salida camión, favor revisar"<br>• `Yard` + modo de salida `Vessel` → inconsistente. Alerta: "Yard - Vessel: un contenedor en patio de transferencia no puede tener modalidad de salida buque, favor revisar" |
| Line Op | Línea naviera. Se usa DOS veces: (a) se valida cruzando contra `LINEA NAVIERA` del Archivo Recinto — si no coincide, solo alerta, no detiene el proceso; (b) es la fuente de las columnas "Id Solicitante" (convertido a código, ver tabla abajo) y "Linea Op" (tal cual, en texto) del documento final. |
| Type Arch ISO | Tipo de contenedor. **Necesario — va al documento final** (campo "Type Arch ISO"), sin variabilidad porque viene de un sistema homologado. |

El resto de las columnas de este archivo (tiene varias más) no se usan.

#### Tabla de equivalencias — Naviera → Código (confirmada con el usuario, para "Id Solicitante")
El campo `Line Op` del Archivo Sistema N4 trae el nombre de la naviera. Como este archivo viene directo de un sistema (no se llena a mano), el usuario confirma que **no hay variabilidad de escritura** aquí — el nombre siempre llega igual. Aun así, el catálogo debe quedar editable porque pueden aparecer navieras nuevas:

| Naviera (Line Op) | Código (para "Id Solicitante") |
|---|---|
| ONE | 4629 |
| CMA | 3472 |
| MSC | 4 |
| HLC | 6375 |
| EVG | 5080 |
| WHL | 5020 |
| COS | 6384 |
| OOL | 3472 |

**Nota:** CMA y OOL comparten el mismo código (3472) — confirmado tal cual lo dio el usuario, no es un error de captura.

**Flujo para agregar una naviera/código nuevo — CONFIRMADO, distinto al de Recinto:**
A diferencia del catálogo de Recintos, aquí **solo el Admin** agrega una naviera y su código nuevos, directamente, sin necesitar aprobación de nadie más (mismo patrón que Motivos/Estatus de NC en Condonaciones). Además, a diferencia de Recinto (donde el código es fijo y solo se agregan nombres/alias), en el catálogo de Navieras el Admin puede dar de alta **tanto el nombre de la naviera como su código**, ya que aquí no se reutilizan códigos existentes — cada naviera nueva puede traer su propio código nuevo. Justificación del usuario: como el dato viene de un sistema y no de captura manual, no hay variabilidad ni errores de dedo que resolver sobre la marcha, así que no hace falta el flujo de propuesta-y-aprobación que sí necesita Recinto.

### Validación de cruce entre los 2 archivos (confirmada con el usuario — ÚNICA VALIDACIÓN BLOQUEANTE del módulo)
- **Campo de cruce confirmado:** `CONTENEDOR` del Archivo Recinto contra `Unit Nbr` del Archivo Sistema N4 (ambos normalizados igual que en Condonaciones: mayúsculas, sin espacios).
- Ambos archivos deben cuadrar al 100% en sus contenedores: mismos números de contenedor en ambos, sin faltantes de ningún lado.
- Si algún contenedor de un archivo no aparece en el otro, se muestra la alerta: **"No se encontró el contenedor X en el archivo Y, favor validar que cuadre la información"**, junto con los totales de cada archivo (ej. "Total contenedores Archivo Recinto: X — Total contenedores Archivo Sistema N4: X").
- **A diferencia de TODAS las demás validaciones de este módulo (que son informativas y nunca detienen el proceso), esta SÍ es bloqueante:** si los archivos no cuadran al 100%, el proceso se detiene por completo — no se genera nada ni se procesa ningún contenedor, ni siquiera los que sí coinciden — hasta que ambos archivos cuadren. Se habilitan nuevamente los campos de carga para que el usuario borre y vuelva a subir los archivos corregidos.
- Confirmado explícitamente por el usuario como la única excepción al principio general de "nunca detener el proceso" que aplica al resto del módulo.
- **BUG CORREGIDO (reportado por el usuario) — contenedores de Importación excluidos del cruce en ambos sentidos:** un contenedor que en el Archivo Recinto viene con `CATEGORIA = IMPORTACION` se elimina de ese archivo (por el filtro de Transbordo), pero SÍ puede seguir apareciendo en el Archivo Sistema N4 (ese archivo no distingue Transbordo/Importación). Antes, esto se marcaba incorrectamente como discrepancia bloqueante. Corregido en `app/transferencias.py`: `procesar_archivo_recinto()` ahora también regresa el set de contenedores que sí vienen en el Recinto pero con categoría distinta de Transbordo (`contenedores_no_transbordo`), y `validar_cruce()` los excluye del cruce. Los únicos contenedores que de verdad importan para el cruce bloqueante son los de **Transbordo**. Dos casos, ambos NO bloquean, solo avisan (`st.warning`, informativo):
  - Contenedor de Importación en Recinto que SÍ aparece en el N4 → aviso "Contenedor(es) ignorado(s) en el cruce porque en el Archivo Recinto son Importación (no Transbordo), aunque sí aparecen en el Archivo Sistema N4: ...".
  - Contenedor de Importación en Recinto que NO aparece en el N4 → aviso "Contenedor(es) de Importación en el Archivo Recinto que no aparecen en el Archivo Sistema N4 (no se consideran en el cruce): ...".
  - Un contenedor que de plano nunca aparece en el Archivo Recinto (ni Transbordo ni Importación) pero sí está en el N4 sigue marcando discrepancia real y bloqueante, como antes — eso no cambió. Verificado con datos de prueba (los 3 escenarios).

### Seguimiento/guardado de cada caso (DISEÑO FINAL CONFIRMADO — mucho más simple que NC)
El usuario aclaró explícitamente que **no quiere un flujo de trabajo con estados como el de NC**: los casos de Transferencias "solo se usan una vez y se desechan" — es decir, no hay un ciclo de vida que dar seguimiento en el tiempo (no hay reasignaciones, no hay reapertura, no hay transición entre estatus). Por eso el guardado de Transferencias es una **bitácora/registro histórico simple**, no un sistema de gestión de casos:

- **Identificación — AJUSTE (ya NO se captura a mano):** el diseño original tenía el folio capturado a mano por el usuario (como el número de NC externo). El usuario después pidió simplificarlo más: ahora el **folio se genera automáticamente, es incremental y único** — texto de 5 dígitos con ceros a la izquierda ('00001', '00002', ...). Se calcula tomando el folio numérico más alto ya guardado en `transferencias_casos` y sumando 1 (`siguiente_folio_transferencia()` en `app/database.py`); si dos personas procesan casi al mismo tiempo y por coincidencia chocara el folio, `registrar_transferencia_auto()` lo detecta y genera el siguiente automáticamente (reintenta hasta 5 veces) — no hay restricción `UNIQUE` a nivel de base de datos, la unicidad se garantiza a nivel de aplicación. El folio ya no es editable ni se pide en el formulario; se asigna y se muestra al usuario (`📋 Folio asignado: ...`) hasta que el caso se guarda con éxito.
- **Responsable — AJUSTE (ya NO se captura a mano):** igual que el folio, esto también se simplificó: ya no es un campo de texto libre editable, se toma automáticamente del nombre del usuario que tiene la sesión iniciada (`usuario['nombre_completo']`). Sigue siendo **puramente informativo** (no vinculado a permisos, no filtra "mis casos"), solo que ahora se llena solo en vez de escribirse a mano.
- **Sin catálogo de estados:** NO existe un equivalente a `nc_estatus` para este módulo. No hay "Pendiente/En proceso/Concluida" ni ninguna otra bandera de estatus — confirmado explícitamente por el usuario, incluso se le ofreció la opción de un estatus mínimo tipo Pendiente/Completado (para saber qué casos ya se subieron a la plataforma externa) y prefirió NO tenerlo.
- **Sin historial de cambios:** al no haber estados que transicionar, no aplica un historial de movimientos como el de NC (`fecha_creacion`/`fecha_actualizacion`/`fecha_cierre` con reapertura, etc.) — el registro queda fijo una vez creado.
- **Qué sí se guarda entonces, por caso:** folio, nombre del responsable (texto libre), fecha de creación, y los datos ya procesados de ese caso (contenedores incluidos, Recinto Origen/Destino con código, y en general lo mismo que terminó en el documento final generado) — para poder consultarlo después como referencia, tal como el módulo "NC Creadas" de Condonaciones sirve de consulta pública de solo lectura, pero aquí SIN estatus ni ciclo de vida que gestionar.

### Reglas de diseño acordadas para este módulo
- Todos los campos se buscan por el **texto del encabezado** (fila 1 del Excel), nunca por posición de columna, para tolerar que el orden de columnas cambie entre archivos.
- Si un campo puede tener variantes de escritura en el encabezado (ej. "No. Contenedor" vs "Contenedor No."), contemplar una lista de alias reconocidos para ese campo — especialmente importante en el Archivo Recinto por ser llenado a mano.
- Lo mismo aplica a VALORES dentro de un campo (no solo encabezados): el caso de Recinto Origen/Destino confirma que los propios valores capturados a mano también necesitan normalización y tablas de alias, no solo los encabezados de columna — y ese catálogo en particular es editable con flujo de propuesta-y-aprobación (ver arriba). El catálogo de Navieras, en cambio, es editable solo por Admin de forma directa, porque su archivo de origen no tiene variabilidad (viene de un sistema, no de captura manual) — **no todos los catálogos de este módulo necesitan el mismo nivel de control**, depende de qué tan confiable es la fuente del dato.
- Si el sistema no reconoce/no encuentra un encabezado esperado, debe avisar claramente **cuál campo faltó**, en vez de fallar en seco o adivinar.
- Todas las validaciones cruzadas de este módulo (formato de contenedor inválido, inconsistencia Inbound/Yard vs Vessel/Truck, línea naviera que no coincide entre archivos) son **alertas informativas que nunca detienen el proceso**, con la ÚNICA EXCEPCIÓN de la validación de cruce de contenedores entre ambos archivos (ver subsección dedicada arriba), que sí es bloqueante — el patrón general aquí es distinto al de Condonaciones, donde varios errores sí bloqueaban el análisis, pero en Transferencias eso se reduce a este único caso.
- Si uno de los 2 archivos subidos resulta erróneo, el proceso **no debe detenerse por completo**: debe existir una opción (cerca de donde se sube cada archivo) para borrarlo y volver a subir uno nuevo, sin perder el resto del avance — similar en espíritu al patrón de re-subida que ya existe en Condonaciones, pero aplicado por archivo individual, no reiniciando todo el análisis.
- Seguimiento/guardado: **CONFIRMADO Y COMPLETO.** A diferencia de NC, Transferencias NO usa un flujo de estados — es una bitácora simple (folio + nombre de responsable informativo + fecha + datos del caso), sin catálogo de estatus, sin historial de transiciones, sin reasignación ni reapertura (ver subsección dedicada "Seguimiento/guardado de cada caso" arriba para el detalle completo).

---

### ✅ ESPECIFICACIÓN COMPLETA — lista para pasar a diseño técnico/programación
Con la definición del seguimiento simplificado (folio + responsable informativo + sin estados), **la especificación funcional del módulo Transferencias ya está completa** al 100%. Ya no queda ningún punto pendiente de confirmar con el usuario. El siguiente paso natural es diseñar la estructura técnica (tabla(s) en Supabase, pantallas en `app.py`, función de generación del Excel) antes de escribir código, siguiendo el mismo patrón ya usado para Condonaciones y Gestión NC.

---

### DISEÑO TÉCNICO PROPUESTO (pendiente de confirmar con el usuario antes de programar)

#### Tablas nuevas en Supabase

**`transferencias_recintos`** — catálogo de recintos (códigos + nombres/alias reconocidos)
```
id, codigo (el código fijo, ej. 6381), nombre (el nombre/alias tal como puede venir escrito,
ej. "SSA MÉXICO"), es_original (bool — true para los 15 alias iniciales ya confirmados,
false para los propuestos por usuarios), aprobado (bool — true para los originales y para
los ya aprobados por Admin; false = pendiente de aprobación pero YA UTILIZABLE de inmediato),
propuesto_por (usuario_id), propuesto_por_nombre, fecha_creacion, aprobado_por, fecha_aprobacion
```
Los 15 alias iniciales se cargan con `es_original=true, aprobado=true`. Un nombre nuevo propuesto por cualquier usuario se guarda con `aprobado=false` pero se usa igual en la fila que lo originó (no bloquea). El código en sí (columna `codigo`) nunca se edita ni se agrega uno nuevo desde la interfaz — solo se agregan nombres relacionados a un código ya existente.

**`transferencias_navieras`** — catálogo de navieras (código + nombre), editable solo por Admin
```
id, codigo, nombre, fecha_creacion
```
Los 8 registros iniciales (ONE, CMA, MSC, HLC, EVG, WHL, COS, OOL) se cargan de una vez. Admin puede agregar naviera+código nuevos directamente desde Usuarios, sin flujo de aprobación (igual que Motivos/Estatus de NC).

**`transferencias_notificaciones`** — aviso a Admin cuando hay un recinto pendiente de aprobar
```
id, usuario_id, recinto_id (FK a transferencias_recintos), mensaje, vista (bool), fecha_creacion
```
Mismo mecanismo de popup al iniciar sesión que ya usa `nc_notificaciones`.

**`transferencias_casos`** — bitácora de cada caso generado (cabecera)
```
id, folio (texto, capturado manualmente), responsable (texto libre, informativo),
usuario_id, usuario_nombre, fecha_creacion, total_contenedores,
total_transbordos, total_importaciones_descartadas
```

**`transferencias_detalle`** — el detalle por contenedor de cada caso (para consulta posterior)
```
id, caso_id (FK a transferencias_casos), contenedor, id_solicitante, linea_op,
type_arch_iso, recinto_origen_codigo, recinto_destino_codigo
```
Este par de tablas es exactamente el mismo patrón que `historial_nc`/`detalle_nc` que ya existe y funciona en Condonaciones — aquí no hace falta inventar nada nuevo, solo reutilizar la idea con los campos propios de Transferencias.

#### Dónde vive en la interfaz
Pestaña nueva de primer nivel, **"🔀 Transferencias"**, con 2 sub-pestañas (igual que Gestión NC usa sub-tabs anidados):
- **📤 Generar Transferencia** — la pantalla principal de trabajo (folio, responsable, carga de los 2 archivos, validaciones, descarga del Excel).
- **📋 Casos Registrados** — tabla pública de solo lectura con buscador (por folio, contenedor o responsable), paginada — igual en espíritu a "NC Creadas", pero sin estatus, solo consulta histórica.

La administración de los catálogos (Recintos y Navieras) vive dentro de la pestaña **"👥 Usuarios"** (solo Admin), como una sección nueva debajo de donde ya están Motivos/Estatus de NC — así no se crea una pestaña extra solo para catálogos.

#### Flujo paso a paso de "📤 Generar Transferencia"
1. Subir **Archivo Recinto**.
2. Subir **Archivo Sistema N4**.
   - **AJUSTE (corregido tras feedback del usuario):** los archivos Excel NO se leen en el momento de subirlos — solo se guarda la referencia del archivo. La lectura pesada (`pd.read_excel`) ocurre una única vez, dentro del botón "Procesar". Esto evita que la página se sienta "recargando" en cada interacción, ya que Streamlit vuelve a correr todo el script en cada clic/tecleo, y antes se releía el Excel en cada una de esas veces.
   - **AJUSTE 2 (pantalla gris al llenar campos):** ambos `file_uploader` están dentro de un `st.form`, así que subirlos ya no dispara el rerender gris de Streamlit — solo se recarga la página una vez, al darle clic a "Procesar". Como efecto secundario, ya no existe el botón "🗑️ Quitar y volver a subir" (no se permite `st.button()` normal dentro de un form); para quitar un archivo se usa la "x" que trae el propio control de subida, y para reiniciar todo el caso sigue estando el botón "🆕 Nuevo caso". El botón "Procesar" tampoco se deshabilita de antemano si falta algo — al darle clic sin algún archivo, aparece un `st.error()` pidiendo completarlo.
   - **AJUSTE 3 (ayuda de columnas requeridas + solo Excel):** debajo de cada `file_uploader` se muestra un texto (`st.caption`) con las columnas que debe tener ese archivo para no marcar error (obligatorias vs. opcionales), y para el Archivo Sistema N4 se recuerda que los encabezados van en la fila 5. Además, ambos `file_uploader` ahora solo aceptan `.xlsx` (`type=["xlsx"]`, antes incluía también `.xls`) — se quitó `.xls` porque `requirements.txt` no trae `xlrd` (la librería que pandas necesita para leer el formato viejo `.xls`), así que un `.xls` real habría tronado con un error confuso en vez de solo ser rechazado limpiamente por el uploader.
   - **AJUSTE 4 (Folio y Responsable ya no se capturan a mano):** se quitaron del formulario los campos de texto de Folio y Responsable — ver el detalle en la sección "Seguimiento/guardado de cada caso" más arriba. El Responsable (usuario en sesión) se muestra arriba del formulario como referencia (`👤 Responsable: ...`), y el Folio se asigna y se muestra (`📋 Folio asignado: ...`) hasta que el caso se guarda con éxito, después de procesar.
3. Botón **"Procesar"** dispara, en orden:
   - Filtrado por `CATEGORIA` (se descartan IMPORTACIÓN) → alerta con totales.
   - Validación de formato de contenedor en ambos archivos → alerta si hay inválidos.
   - **AJUSTE (pedido por el usuario) — contenedores de Transbordo duplicados:** en `procesar_archivo_recinto()` (`app/transferencias.py`), después del filtro de categoría, se detectan contenedores de Transbordo que aparecen más de una vez en el Archivo Recinto (pasa seguido cuando la persona que captura el archivo a mano no está segura de si ya puso el contenedor, con archivos de muchas filas).
     - Primera versión: solo informativa, sin quitar nada — pero el usuario hizo notar que el archivo Sistema N4 **nunca duplica un contenedor** (el sistema de origen siempre da un solo registro, el más reciente), así que si el duplicado en Recinto no se resolvía, el contenedor terminaba repetido en el documento final.
     - **Se le presentaron 3 opciones al usuario (AskUserQuestion) y eligió: "Quedarse con la fila más reciente".** Comportamiento final: nunca bloquea el proceso, pero SÍ se resuelve automáticamente — se conserva la ÚLTIMA fila de ese contenedor en el archivo (la más abajo = la más reciente, igual que el criterio de N4) y se descartan las filas anteriores repetidas (`df.drop_duplicates(subset="CONTENEDOR", keep="last")`). Sigue apareciendo el aviso informativo: "Contenedor(es) de Transbordo duplicado(s) en el Archivo Recinto: se conservó el registro más reciente (la última fila) de cada uno y se descartaron las repeticiones anteriores, favor de validar que sea correcto: ...". Verificado con datos de prueba, incluyendo un caso donde las filas duplicadas tenían Recinto Destino distinto (se confirmó que se queda con el de la fila más reciente).
   - **Cruce de contenedores** `CONTENEDOR` vs `Unit Nbr`, SOLO entre los de Transbordo — si no cuadran al 100%, se **detiene el proceso** con el mensaje de alerta ya definido y se vuelve a habilitar la carga de archivos. Los contenedores de Importación (excluidos del Recinto) nunca participan en este cruce bloqueante — como mucho generan un aviso informativo (ver bug corregido arriba).
   - Si cuadran: validaciones no-bloqueantes (LINEA NAVIERA vs Line Op, T-State vs O/B Dclrd Mode, T-State vs Stop-Vsl/Stop-Road) → alertas informativas, se sigue de largo.
     - **AJUSTE (pedido por el usuario) — bloqueos Stop-Vsl / Stop-Road:** el Archivo Sistema N4 puede traer dos columnas opcionales, `Stop-Vsl` y `Stop-Road` (valores `true`/`false`), que indican si hay un bloqueo específico para una modalidad de salida del contenedor: `Stop-Vsl` = bloqueo modalidad de salida buque, `Stop-Road` = bloqueo modalidad de salida camión. Se agregó una validación informativa (nunca bloquea) en `procesar_archivo_n4()` de `app/transferencias.py`:
       - Contenedor con `T-State = Yard` y `Stop-Road = true` → alerta "Se detectó que el contenedor en patio tiene bloqueo modalidad de salida camión, favor validar".
       - Contenedor con `T-State = Inbound` y `Stop-Vsl = true` → alerta "Se detectó que el contenedor pendiente de ingresar tiene bloqueo modalidad de salida buque, favor validar".
       - Los valores true/false se interpretan con una función nueva `es_valor_verdadero()` (en `app/transferencias_config.py`) que acepta booleano de Python, 1/0, o texto "TRUE"/"FALSE"/"VERDADERO"/"FALSO"/"SI", sin importar mayúsculas ni espacios — cualquier otra cosa (vacío, columna ausente, etc.) se toma como `false` sin tronar. Alias de encabezado agregados a `COL_N4_ALIAS`: `stop_vsl` y `stop_road`. Verificado con datos de prueba (con y sin las columnas, con texto y con booleano).
   - Resolución de Recinto Origen/Destino contra el catálogo → si hay nombres no reconocidos, se abre el flujo de "proponer nombre nuevo" (selector del código existente al que se quiere asociar) y se sigue procesando con el código elegido.
     - **AJUSTE (pedido por el usuario) — salida para nombres que son error de captura:** en esta pantalla, junto al botón "💾 Guardar relaciones y reprocesar", hay un segundo botón "🔙 Corregir archivo (cancelar y volver a subir)" con una leyenda de advertencia arriba explicando que si el nombre no reconocido es un error de captura o una prueba (ej. "xd", "triple y" — no es un recinto real), lo correcto es corregir el Archivo Recinto y volver a subirlo, no relacionarlo con un código cualquiera. Ese botón cancela el caso actual sin proponer ningún nombre nuevo y regresa a la pantalla de subida (mismo reset que "🆕 Nuevo caso", pero sin tocar el folio/responsable ya que esos ahora son automáticos).
     - **AJUSTE 2 (pedido por el usuario) — catálogo visible como referencia:** arriba de la lista de nombres a relacionar se muestra, ya abierto (`st.expander(..., expanded=True)`), el catálogo actual de Recintos agrupado por código (ej. "6381 → SSA, SSA MEXICO, SSA MÉXICO..."), incluyendo nombres aún pendientes de aprobar (marcados "(pendiente)"). Así, si el nombre no reconocido viene escrito de forma "creativa" o poco común, el usuario puede ver de un vistazo con qué código ya existente se relaciona en vez de adivinar.
   - Resolución de Naviera → código para "Id Solicitante".
4. Se genera el Excel final (columna A vacía y angosta, datos desde columna B, 8 columnas, `Id Estado Contenedor=1` y `Trucking` fijos) y se guarda en `session_state` para no regenerarse en cada rerender (mismo patrón que `reporte_bytes`).
5. Justo después de generar el Excel (no hasta que se descargue), se asigna el folio automático y se guarda el caso en `transferencias_casos` + `transferencias_detalle` vía `registrar_transferencia_auto()` (protegido por la bandera `trans_guardado` para no duplicar el registro en cada rerender).
6. Botón **"⬇️ Descargar documento final (Excel)"** — solo aparece una vez que el caso ya se guardó con éxito (con su folio asignado en el nombre del archivo).
7. Botón **"Nuevo caso"** para limpiar todo y volver a empezar.

#### Administración de catálogos (dentro de "👥 Usuarios")
- **Recintos:** tabla de solo lectura (código + nombres relacionados); formulario para que cualquier usuario proponga un nombre nuevo asociado a un código existente; sección aparte, visible solo para Admin, con los nombres pendientes de aprobar (aprobar/rechazar).
- **Navieras:** tabla editable directamente por Admin (agregar naviera + código nuevos).

**Este diseño técnico fue aprobado por el usuario ("dale para adelante") y YA SE PROGRAMÓ.**

### ✅ IMPLEMENTADO — estado del código

- `app/transferencias_config.py` (NUEVO) — mapeo de columnas con alias por texto de encabezado, catálogos iniciales (14 alias de Recinto, 8 de Naviera — "CONTECON con espacio al final" no necesitó fila aparte porque la normalización ya quita espacios extra), normalización de texto.
- `app/transferencias.py` (NUEVO) — lectura y validación de ambos archivos, cruce bloqueante `CONTENEDOR`/`Unit Nbr`, validaciones no bloqueantes (Inbound/Yard vs Truck/Vessel, LINEA NAVIERA vs Line Op), resolución de Recinto/Naviera contra catálogo. Probado con datos de ejemplo (filtro CATEGORIA, alertas, cruce bloqueante y resolución con override todos verificados).
- `app/transferencias_reporte.py` (NUEVO) — genera el Excel final: columna A vacía y angosta, datos desde columna B, 8 columnas en el orden confirmado, `Id Estado Contenedor=1` y `Trucking` fijos. Verificado con un caso de prueba.
- `app/database.py` (MODIFICADO) — se agregaron funciones para: catálogo de Recintos (obtener/proponer/aprobar/rechazar), catálogo de Navieras (obtener/crear/eliminar), notificaciones de Transferencias, y la bitácora (`registrar_transferencia`, `obtener_transferencias_casos`, `obtener_transferencias_detalle`, `folio_transferencia_existe`, `siguiente_folio_transferencia`, `registrar_transferencia_auto`) — las últimas dos son las que generan el folio automático incremental y guardan el caso con reintento si hay coincidencia de folio.
- `app.py` (MODIFICADO) — nueva pestaña **"🔀 Transferencias"** (visible para todos los usuarios) con sub-pestañas "📤 Generar Transferencia" y "📋 Casos Registrados"; sección de administración de catálogos (Recintos y Navieras) agregada al final de la pestaña "👥 Usuarios" (solo Admin); notificaciones de Transferencias incluidas en el popup de notificaciones al iniciar sesión.
- `sql_transferencias.sql` (NUEVO) — script para crear las 5 tablas nuevas en Supabase (`transferencias_recintos`, `transferencias_navieras`, `transferencias_notificaciones`, `transferencias_casos`, `transferencias_detalle`) con RLS + política `service_role`, más los datos iniciales de ambos catálogos.

**Pendiente para el usuario (fuera de este documento):**
1. Correr `sql_transferencias.sql` completo en el SQL Editor de Supabase.
2. Subir `app.py` y los archivos de `app/` (los modificados y los nuevos) a GitHub, reemplazando el contenido de cada uno.
3. Probar el módulo con archivos reales de Recinto y Sistema N4 antes de usarlo en producción — todavía no se ha probado con datos reales, solo con datos de ejemplo construidos a mano.


---
## Perfiles de Análisis con aprobación y Días Especiales globales (oct 2026)

**Perfiles:** el perfil `usuario` ya NO crea perfiles: pulsa "📨 Solicitar" y se guarda en `perfiles_solicitudes` (estado pendiente). Editar y eliminar perfiles es solo admin. El admin ve en Análisis el cuadro "🔔 Solicitudes de perfil pendientes" con ✅ Aprobar (crea el perfil real con `crear_perfil_db`) o ❌ Rechazar (motivo obligatorio). Avisos: al iniciar sesión el admin recibe un toast con el número de pendientes; el usuario recibe toast de autorizada/rechazada (con motivo) una sola vez (`notificado`), y ve "📨 Mis solicitudes de perfil".

**Días especiales:** ahora son GLOBALES, guardados en tabla `dias_especiales` (fecha PK, comentario, creado_por). Solo el admin los marca/quita: clic en un día → panel con comentario obligatorio → "Marcar como especial" (o "Quitar"). Al pasar el mouse sobre un día especial se ve el comentario; sobre un festivo, su nombre (`nombre_festivo()` en `app/calendario.py`). Un análisis ignora los días especiales anteriores al ingreso del contenedor sin borrarlos. Botón "Limpiar" solo admin con confirmación. El archivo JSON antiguo `festivos_especiales.json` ya no se usa.

**SQL:** `SQL_perfiles_y_dias_especiales.sql` (tablas `perfiles_solicitudes` y `dias_especiales`). Funciones nuevas en `database.py`: `crear_solicitud_perfil`, `obtener_solicitudes_perfil`, `resolver_solicitud_perfil`, `obtener_solicitudes_perfil_sin_notificar`, `marcar_solicitudes_perfil_notificadas`, `obtener_dias_especiales_db`, `agregar_dia_especial_db`, `quitar_dia_especial_db`, `limpiar_dias_especiales_db`.
