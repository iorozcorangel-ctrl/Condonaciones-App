"""
================================================================
  SISTEMA DE CONDONACIONES — TERMINAL PORTUARIA PACÍFICO
  Versión Web — Streamlit + Supabase
================================================================
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime
from zoneinfo import ZoneInfo
import io
import calendar
import hashlib

ZONA_MX = ZoneInfo("America/Mexico_City")

def hoy_mx():
    """Retorna la fecha actual en zona horaria de México."""
    return datetime.now(ZONA_MX).date()


# ── Wrappers con caché corto para evitar golpear Supabase en cada
#    rerun de Streamlit (todas las pestañas se ejecutan siempre,
#    aunque no estén visibles, así que cachear reduce mucho la carga) ──
@st.cache_data(ttl=8, show_spinner=False)
def _cached_nc_asignaciones():
    return obtener_nc_asignaciones()

@st.cache_data(ttl=15, show_spinner=False)
def _cached_usuarios():
    return obtener_usuarios()

@st.cache_data(ttl=30, show_spinner=False)
def _cached_nc_motivos():
    return obtener_nc_motivos()

@st.cache_data(ttl=30, show_spinner=False)
def _cached_nc_estatus():
    return obtener_nc_estatus()


def invalidar_cache_nc():
    """Llamar después de crear/editar/eliminar una NC para refrescar la vista al instante."""
    _cached_nc_asignaciones.clear()

from app.config import COL_BI, COL_TAB
# Perfiles ahora vienen de Supabase via database.py
from app.calendario import get_festivos_oficiales
from app.validaciones import (validar_archivos, aplicar_regla1, aplicar_regla2,
                               calcular_desfases, calcular_montos)
from app.reporte import generar_reporte
from app.database import (login_usuario, obtener_usuarios, crear_usuario,
                           cambiar_password, toggle_usuario, eliminar_usuario,
                           registrar_nc, verificar_duplicados,
                           obtener_historial, obtener_detalle_nc, eliminar_nc,
                           obtener_perfiles, crear_perfil_db, modificar_perfil_db,
                           eliminar_perfil_db, guardar_ultimo_perfil_db,
                           obtener_ultimo_perfil_db,
                           guardar_previo_borrador, cargar_borradores_previo,
                           eliminar_borradores_nc, hay_borrador_activo,
                           extraer_contenedores, obtener_nc_motivos, crear_nc_motivo,
                           editar_nc_motivo, eliminar_nc_motivo,
                           obtener_nc_estatus, crear_nc_estatus, editar_nc_estatus,
                           eliminar_nc_estatus,
                           crear_nc_asignacion, obtener_nc_asignaciones,
                           obtener_nc_por_id, actualizar_nc_asignacion,
                           reasignar_nc, inhabilitar_nc, marcar_seguimiento_nc,
                           concluir_nc, reabrir_nc, buscar_nc_asignaciones,
                           actualizar_herencia_analisis,
                           obtener_notificaciones_pendientes,
                           marcar_notificaciones_vistas,
                           verificar_contenedores_en_nc,
                           registrar_duplicado_revisado)

st.set_page_config(
    page_title="Mi Mini Puerto: Solicitudes de reclamo",
    page_icon="🚢",
    layout="wide"
)

st.markdown("""
<style>
.topbar{background:#E65100;padding:16px 24px;border-radius:8px;margin-bottom:20px;}
.topbar h1{color:white;font-size:22px;margin:0;font-weight:600;}
.topbar p{color:#FFCC80;font-size:13px;margin:4px 0 0 0;}
.sec-hdr{background:#E65100;color:white;padding:8px 14px;border-radius:6px;
         font-weight:600;font-size:14px;margin-bottom:12px;}
.admin-hdr{background:#BF360C;color:white;padding:8px 14px;border-radius:6px;
           font-weight:600;font-size:14px;margin-bottom:12px;}
.badge-admin{background:#BF360C;color:white;padding:2px 10px;border-radius:20px;
             font-size:12px;font-weight:600;}
.badge-user{background:#E65100;color:white;padding:2px 10px;border-radius:20px;
            font-size:12px;font-weight:600;}
</style>
""", unsafe_allow_html=True)

# ── Estado inicial ──────────────────────────────────────────────
def init():
    defs = {
        "usuario":           None,       # dict con datos del usuario logueado
        "df_tab":            None,
        "df_bi":             None,
        "df_tab_v":          None,
        "df_bi_v":           None,
        "perfiles":          [],
        "perfil_idx":        0,
        "perfiles_cargados": False,
        "dias_especiales":   set(),
        "paso":              "inicio",
        "desfases":          {},
        "montos":            {},
        "fecha_solicitud":   None,
        "nc_cliente":        "",
        "fecha_revision":    hoy_mx(),
        "cal_anio":          hoy_mx().year,
        "cal_mes":           hoy_mx().month,
        "mostrar_form_perfil": None,
        "alertas":           [],
        "uploader_key":      0,
        "vista":             "analisis",  # analisis | historial | usuarios
        "cond_manual":       False,
        "dias_manual_previo": 0,
        "dias_manual_ffcc":   0,
        "dias_manual_carr":   0,
        "nc_reset":          False,
        "nc_val":            "",
        "fecha_val":         None,
        "previo_manual_activo": False,
        "contadores_previo": {},
        "paso_previo":       "inicio",
    }
    for k, v in defs.items():
        if k not in st.session_state:
            st.session_state[k] = v

init()

# ── Restaurar sesión desde token en URL ─────────────────────────
# El token en la URL persiste en F5 pero NO entre cierres de navegador
# ya que la sesión expira por inactividad (3 horas)
if not st.session_state.get("autenticado"):
    try:
        params = st.query_params
        token  = params.get("sid", "")
        if token:
            from app.database import verificar_sesion as _vs
            usuario_tok = _vs(token)  # También actualiza última actividad
            if usuario_tok:
                st.session_state["autenticado"]   = True
                st.session_state["usuario"]       = usuario_tok
                st.session_state["session_token"] = token
                st.rerun()
            else:
                # Token inválido o expirado por inactividad — limpiar URL
                st.query_params.clear()
    except Exception:
        pass

# ════════════════════════════════════════════════════════════════
#   PANTALLA DE LOGIN
# ════════════════════════════════════════════════════════════════
if not st.session_state.get("autenticado") or st.session_state.get("usuario") is None:
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("""
        <div style='text-align:center;padding:40px 0 20px;'>
          <h2 style='color:#E65100;'>🚢 Mi Mini Puerto</h2>
          <p style='color:#666;'>Terminal Portuaria Pacífico</p>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login"):
            username = st.text_input("Usuario", placeholder="Ingresa tu usuario")
            password = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Entrar", use_container_width=True):
                if not username or not password:
                    st.warning("Ingresa usuario y contraseña")
                else:
                    with st.spinner("Verificando..."):
                        usuario = login_usuario(username, password)
                    if usuario:
                        st.session_state["autenticado"]   = True
                        st.session_state["usuario"]       = usuario
                        # Crear sesión en BD y guardar token en URL
                        from app.database import crear_sesion as _cs
                        tok = _cs(usuario["id"], usuario["username"])
                        if tok:
                            st.session_state["session_token"] = tok
                            st.query_params["sid"] = tok
                        st.rerun()
                    else:
                        st.error("Usuario o contraseña incorrectos")
    st.stop()

# ════════════════════════════════════════════════════════════════
#   APP PRINCIPAL — Usuario autenticado
# ════════════════════════════════════════════════════════════════

usuario     = st.session_state["usuario"]
es_admin    = usuario["rol"] == "admin"

# ── Verificar inactividad — solo cada 2 minutos, no en cada render ──
# (evita un round-trip a Supabase por cada clic, que hacía sentir lenta la app)
import time as _time
_ultima_verif = st.session_state.get("_ultima_verif_sesion", 0)
if st.session_state.get("session_token") and (_time.time() - _ultima_verif > 120):
    from app.database import verificar_sesion as _vs2
    _check = _vs2(st.session_state["session_token"])
    st.session_state["_ultima_verif_sesion"] = _time.time()
    if not _check:
        # Sesión expirada por inactividad
        st.query_params.clear()
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ── Cargar perfiles desde Supabase si no están cargados ────────
if not st.session_state.get("perfiles_cargados", False):
    perfiles_db = obtener_perfiles()
    # Deduplicar: si hay más de un Default, conservar solo el primero
    vistos_default = False
    perfiles_unicos = []
    for p in perfiles_db:
        if p.get("es_default"):
            if not vistos_default:
                perfiles_unicos.append(p)
                vistos_default = True
        else:
            perfiles_unicos.append(p)
    st.session_state["perfiles"] = perfiles_unicos
    st.session_state["perfiles_cargados"] = True
    # Restaurar último perfil usado
    ultimo_id = obtener_ultimo_perfil_db(usuario["id"])
    if ultimo_id:
        for i, p in enumerate(perfiles_db):
            if p.get("id") == ultimo_id:
                st.session_state["perfil_idx"] = i
                break
nombre_user = usuario["nombre_completo"]
rol_badge   = "badge-admin" if es_admin else "badge-user"
rol_label   = "Administrador" if es_admin else "Usuario"

# ── Barra superior ──────────────────────────────────────────────
col_titulo, col_user = st.columns([4, 1])
with col_titulo:
    st.markdown("""
    <div class='topbar'>
      <h1>🚢 Mi Mini Puerto: Solicitudes de reclamo</h1>
      <p>Terminal Portuaria · Análisis de Condonaciones</p>
    </div>
    """, unsafe_allow_html=True)
with col_user:
    st.markdown(f"""
    <div style='padding:12px;background:var(--background-color);border-radius:8px;
                border:1px solid #ddd;margin-top:4px;'>
      <div style='font-size:13px;font-weight:600;'>{nombre_user}</div>
      <span class='{rol_badge}'>{rol_label}</span>
    </div>
    """, unsafe_allow_html=True)
    if st.button("🚪 Salir", use_container_width=True):
        try:
            from app.database import eliminar_sesion as _es
            _es(st.session_state.get("session_token", ""))
            st.query_params.clear()
        except Exception:
            pass
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ── Navegación ──────────────────────────────────────────────────
tabs_disponibles = ["📊 Análisis", "📋 Historial NC", "📖 Reglas de Aplicación",
                    "🗂️ Gestión NC"]
if es_admin:
    tabs_disponibles.append("👥 Usuarios")

# Índices dinámicos según el rol
IDX_GESTION  = 3
IDX_USUARIOS = 4 if es_admin else None

# ── Popup de notificaciones al iniciar sesión ───────────────────
if not st.session_state.get("notif_mostrado", False):
    notifs = obtener_notificaciones_pendientes(usuario["id"])
    if notifs:
        with st.container():
            st.info("🔔 **Notificaciones pendientes:**\n\n" + "\n\n".join(
                f"• {n['mensaje']}" for n in notifs
            ))
        marcar_notificaciones_vistas(usuario["id"])
    st.session_state["notif_mostrado"] = True

nav = st.tabs(tabs_disponibles)

# ════════════════════════════════════════════════════════════════
#   PESTAÑA 1 — ANÁLISIS
# ════════════════════════════════════════════════════════════════
with nav[0]:
    col_izq, col_der = st.columns([3, 2])
    bloqueado = st.session_state["paso"] != "inicio"

    with col_izq:
        # ── Perfil ────────────────────────────────────────────
        st.markdown("<div class='sec-hdr'>Perfil de Condonación</div>",
                    unsafe_allow_html=True)
        perfiles = st.session_state["perfiles"]
        nombres  = [p["nombre"] for p in perfiles]
        idx      = min(st.session_state["perfil_idx"], len(perfiles)-1)

        c1, c2, c3, c4 = st.columns([3,1,1,1])
        with c1:
            sel = st.selectbox("Perfil", nombres, index=idx,
                               label_visibility="collapsed", disabled=bloqueado)
            nuevo_idx = nombres.index(sel)
            if nuevo_idx != st.session_state["perfil_idx"]:
                st.session_state["perfil_idx"] = nuevo_idx
                perfil_sel = perfiles[nuevo_idx]
                perfil_sel_id = perfil_sel.get("id", "")
                if perfil_sel_id:
                    guardar_ultimo_perfil_db(usuario["id"], perfil_sel_id)
        with c2:
            if st.button("➕ Nuevo", use_container_width=True, disabled=bloqueado):
                st.session_state["mostrar_form_perfil"] = "nuevo"
        with c3:
            if st.button("✏️ Editar", use_container_width=True,
                         disabled=nuevo_idx==0 or bloqueado):
                st.session_state["mostrar_form_perfil"] = "editar"
        with c4:
            if st.button("🗑️", use_container_width=True,
                         disabled=nuevo_idx==0 or bloqueado):
                perfil_id = perfiles[nuevo_idx].get("id", "")
                if perfil_id:
                    eliminar_perfil_db(perfil_id)
                st.session_state["perfiles"].pop(nuevo_idx)
                st.session_state["perfil_idx"] = 0
                st.rerun()

        if st.session_state["mostrar_form_perfil"]:
            modo = st.session_state["mostrar_form_perfil"]
            p    = perfiles[nuevo_idx] if modo == "editar" else {}
            with st.expander("Configurar Perfil", expanded=True):
                nombre_p = st.text_input("Nombre", value=p.get("nombre",""))
                r1 = st.checkbox("Aplicar regla 30 días (Regla 1)",
                                  value=p.get("regla1_activa", True))
                r2 = st.checkbox("Aplicar regla 4 días (Regla 2)",
                                  value=p.get("regla2_activa", True))
                pc1, pc2, pc3 = st.columns(3)
                na_p = pc1.checkbox("R3: No aplica previo",
                                    value=p.get("na_previo", False))
                na_f = pc2.checkbox("R4: No aplica FFCC",
                                    value=p.get("na_ffcc", False))
                na_c = pc3.checkbox("R5: No aplica carretero",
                                    value=p.get("na_carretero", False))
                pc4, pc5, pc6 = st.columns(3)
                dp = pc4.number_input("Días previo (R3)", 1, 30,
                                       p.get("dias_previo", 3),
                                       disabled=na_p)
                df = pc5.number_input("Días FFCC (R4)", 1, 30,
                                       p.get("dias_ferromex", 3),
                                       disabled=na_f)
                dc = pc6.number_input("Días carretero (R5)", 1, 30,
                                       p.get("dias_carretero", 2),
                                       disabled=na_c)
                bg1, bg2 = st.columns(2)
                if bg1.button("💾 Guardar", use_container_width=True):
                    if nombre_p:
                        np2 = {"nombre": nombre_p, "es_default": False,
                               "regla1_activa": r1, "regla2_activa": r2,
                               "dias_previo": dp, "dias_ferromex": df,
                               "dias_carretero": dc,
                               "na_previo": na_p, "na_ffcc": na_f,
                               "na_carretero": na_c}
                        if modo == "nuevo":
                            ok_p, data_p = crear_perfil_db(np2)
                            if ok_p:
                                np2["id"] = data_p.get("id", "")
                                st.session_state["perfiles"].append(np2)
                                st.session_state["perfil_idx"] = len(st.session_state["perfiles"]) - 1
                        else:
                            perfil_id = st.session_state["perfiles"][nuevo_idx].get("id", "")
                            modificar_perfil_db(perfil_id, np2)
                            np2["id"] = perfil_id
                            st.session_state["perfiles"][nuevo_idx] = np2
                        st.session_state["mostrar_form_perfil"] = None
                        st.rerun()
                if bg2.button("Cancelar", use_container_width=True):
                    st.session_state["mostrar_form_perfil"] = None
                    st.rerun()

        # ── Resumen informativo del perfil ────────────────────
        perfil_activo = st.session_state["perfiles"][nuevo_idx]
        r1_txt  = "✅ Activa" if perfil_activo.get("regla1_activa", True) else "❌ Desactivada"
        r2_txt  = "✅ Activa" if perfil_activo.get("regla2_activa", True) else "❌ Desactivada"
        dp_txt  = "🚫 No aplica" if perfil_activo.get("na_previo", False) else f"{perfil_activo.get('dias_previo', 3)} días hábiles"
        df_txt  = "🚫 No aplica" if perfil_activo.get("na_ffcc", False) else f"{perfil_activo.get('dias_ferromex', 3)} días naturales"
        dc_txt  = "🚫 No aplica" if perfil_activo.get("na_carretero", False) else f"{perfil_activo.get('dias_carretero', 2)} días hábiles"
        st.markdown(f"""
        <div style='background:#FFF3E0;border-left:4px solid #E65100;padding:10px 14px;
                    border-radius:4px;font-size:13px;color:#555;margin-bottom:8px;'>
        <b>Configuración del perfil activo:</b><br>
        📅 <b>Regla 1</b> — Validación 30 días naturales: {r1_txt}<br>
        📅 <b>Regla 2</b> — Validación primeros 4 días: {r2_txt}<br>
        🔄 <b>Regla 3</b> — Plazo para posicionamiento de previo: <b>{dp_txt}</b><br>
        🚂 <b>Regla 4</b> — Plazo para carga a góndola FFCC: <b>{df_txt}</b><br>
        🚚 <b>Regla 5</b> — Plazo para entrega carretero: <b>{dc_txt}</b>
        </div>
        """, unsafe_allow_html=True)

        # ── Datos de solicitud ────────────────────────────────
        st.markdown("<div class='sec-hdr'>Datos de Solicitud</div>",
                    unsafe_allow_html=True)
        dc1, dc2 = st.columns(2)
        # Reset NC y fecha — usar input_key para forzar re-render
        ikey = st.session_state["uploader_key"]

        # ── Campo único de N° NC — solo se puede elegir de la lista ───
        nc_asignadas_disp = _cached_nc_asignaciones()
        # Deduplicar nombres conservando orden
        nombres_nc_asig = []
        for nc in nc_asignadas_disp:
            if nc["nc_externo"] not in nombres_nc_asig:
                nombres_nc_asig.append(nc["nc_externo"])

        if not nombres_nc_asig:
            dc1.info("No hay NCs asignadas aún. Pide al administrador que "
                     "cree una en Gestión NC → Asignar NC.")
            nc_input = ""
        else:
            opciones_nc = ["-- Selecciona una NC --"] + sorted(nombres_nc_asig)
            nc_sel = dc1.selectbox("N° Nota de Crédito",
                                   opciones_nc, disabled=bloqueado,
                                   key=f"nc_sel_{ikey}")
            nc_input = "" if nc_sel == "-- Selecciona una NC --" else nc_sel

        with dc2:
            fecha_picker = st.date_input("Fecha Solicitud NC",
                                          value=hoy_mx(),
                                          format="DD/MM/YYYY",
                                          disabled=bloqueado,
                                          key=f"fecha_picker_{ikey}")
            fecha_picker = fecha_picker if fecha_picker else hoy_mx()
            fecha_input = fecha_picker.strftime("%d/%m/%Y")
        st.caption("La fecha aplica a todos los contenedores.")

        # ── Condonación Manual Directa ────────────────────────
        st.markdown("<div class='sec-hdr'>Condonación Manual Directa</div>",
                    unsafe_allow_html=True)
        cond_manual_check = st.checkbox(
            "Realizar condonación manual directa (omite cálculo automático de desfases)",
            value=st.session_state["cond_manual"],
            disabled=bloqueado
        )
        st.session_state["cond_manual"] = cond_manual_check

        if cond_manual_check:
            st.caption("⚠️ Las reglas 3, 4 y 5 se omiten. Los días ingresados se usan directamente para calcular la condonación.")
            cm1, cm2, cm3 = st.columns(3)
            dias_m_previo = cm1.number_input("🔄 Días previo",      min_value=0, value=st.session_state["dias_manual_previo"], disabled=bloqueado)
            dias_m_ffcc   = cm2.number_input("🚂 Días ferroviario", min_value=0, value=st.session_state["dias_manual_ffcc"],   disabled=bloqueado)
            dias_m_carr   = cm3.number_input("🚚 Días carretero",   min_value=0, value=st.session_state["dias_manual_carr"],   disabled=bloqueado)
            st.session_state["dias_manual_previo"] = dias_m_previo
            st.session_state["dias_manual_ffcc"]   = dias_m_ffcc
            st.session_state["dias_manual_carr"]   = dias_m_carr

        # ── Archivos ──────────────────────────────────────────
        st.markdown("<div class='sec-hdr'>Archivos de Entrada</div>",
                    unsafe_allow_html=True)
        ukey = st.session_state["uploader_key"]
        fa1, fa2 = st.columns(2)
        with fa1:
            f_tab = st.file_uploader("📋 Tabulador Comercial",
                                      type=["xlsx","xls"],
                                      key=f"tab_{ukey}",
                                      disabled=bloqueado)
            if f_tab:
                try:
                    st.session_state["df_tab"] = pd.read_excel(f_tab)
                    st.success(f"✔ {f_tab.name}")
                except Exception as e:
                    st.error(str(e))
        with fa2:
            f_bi = st.file_uploader("📊 Archivo BI",
                                     type=["xlsx","xls"],
                                     key=f"bi_{ukey}",
                                     disabled=bloqueado)
            if f_bi:
                try:
                    st.session_state["df_bi"] = pd.read_excel(f_bi)
                    st.success(f"✔ {f_bi.name}")
                except Exception as e:
                    st.error(str(e))

        # ── Botones principales ───────────────────────────────
        st.markdown("---")
        ambos = (st.session_state["df_tab"] is not None and
                 st.session_state["df_bi"] is not None)

        bb1, bb2 = st.columns(2)
        with bb1:
            iniciar = st.button("▶ Iniciar Análisis",
                                disabled=not ambos or bloqueado,
                                use_container_width=True, type="primary")
        with bb2:
            if st.button("↺ Nuevo Análisis", use_container_width=True):
                st.session_state["df_tab"]             = None
                st.session_state["df_bi"]              = None
                st.session_state["df_tab_v"]           = None
                st.session_state["df_bi_v"]            = None
                st.session_state["desfases"]           = {}
                st.session_state["montos"]             = {}
                st.session_state["alertas"]            = []
                st.session_state["paso"]               = "inicio"
                st.session_state["uploader_key"] += 1
                st.rerun()

        # ── Mostrar alertas acumuladas ────────────────────────
        if st.session_state["alertas"]:
            st.markdown("---")
            st.markdown("### Alertas del análisis")
            for tipo, msg in st.session_state["alertas"]:
                if tipo == "warning":
                    st.warning(msg)
                elif tipo == "info":
                    st.info(msg)
                elif tipo == "error":
                    st.error(msg)
                elif tipo == "duplicado":
                    st.error(msg)

        # ════════════════════════════════════════════════════
        #   FLUJO: INICIAR ANÁLISIS
        # ════════════════════════════════════════════════════
        if iniciar:
            try:
                fecha_sol = datetime.strptime(fecha_input, "%d/%m/%Y").date()
            except ValueError:
                st.error("Formato de fecha inválido. Use DD/MM/AAAA")
                st.stop()

            if not nc_input.strip():
                st.warning("Ingrese el número de nota de crédito")
                st.stop()

            perfil  = st.session_state["perfiles"][st.session_state["perfil_idx"]]
            alertas = []

            with st.spinner("Validando archivos..."):
                df_tv, df_bv, errores, advertencias = validar_archivos(
                    st.session_state["df_tab"].copy(),
                    st.session_state["df_bi"].copy()
                )

            if errores:
                for e in errores:
                    st.error(e)
                st.session_state["df_tab"]       = None
                st.session_state["df_bi"]        = None
                st.session_state["uploader_key"] += 1
                st.rerun()

            for a in advertencias:
                alertas.append(("warning", a))

            # ── Verificar duplicados en BD ────────────────────
            # ── Validar días del calendario contra TimeIn ────────
            from app.validaciones import to_date as _to_date
            timein_dates = [_to_date(row.get(COL_BI["time_in"]))
                           for _, row in df_bv.iterrows()
                           if _to_date(row.get(COL_BI["time_in"]))]
            if timein_dates:
                timein_min = min(timein_dates)
                dias_invalidos = [d for d in st.session_state["dias_especiales"]
                                  if d < timein_min]
                if dias_invalidos:
                    # Desmarcar los días inválidos automáticamente
                    for d in dias_invalidos:
                        st.session_state["dias_especiales"].discard(d)
                    alertas.append(("warning",
                        f"⚠️ Día(s) marcado(s) en el calendario anteriores al "
                        f"ingreso del contenedor ({timein_min.strftime('%d/%m/%Y')}). "
                        f"Se desmarcaron automáticamente."))

            with st.spinner("Verificando duplicados en historial..."):
                contenedores_list = df_bv[COL_BI["contenedor"]].tolist()
                facturas_list     = df_bv[COL_BI["no_factura"]].tolist() if COL_BI["no_factura"] in df_bv.columns else []
                duplicados        = verificar_duplicados(contenedores_list, facturas_list)

            if duplicados:
                for dup in duplicados:
                    if dup["tipo"] == "ERROR":
                        alertas.append(("warning",
                            f"⚠️ No se pudo verificar duplicados en el historial: {dup['valor']}"))
                    elif dup["tipo"] == "Factura":
                        alertas.append(("duplicado",
                            f"⚠️ **Factura duplicada:** La factura **{dup['valor']}** "
                            f"del contenedor **{dup['contenedor']}** ya fue registrada "
                            f"en la NC **{dup['nc_anterior']}** (fecha: {dup['fecha']}). "
                            f"Verifique antes de continuar."))
                    elif dup["tipo"] == "Contenedor":
                        alertas.append(("duplicado",
                            f"⚠️ **Contenedor duplicado:** El contenedor **{dup['valor']}** "
                            f"ya fue registrado en la NC **{dup['nc_anterior']}** "
                            f"(fecha: {dup['fecha']}). Verifique antes de continuar."))

            with st.spinner("Calculando desfases..."):
                # Aplicar NA del perfil
                perfil_act = st.session_state["perfiles"][st.session_state["perfil_idx"]]
                if st.session_state["cond_manual"]:
                    dp_m = int(st.session_state["dias_manual_previo"])
                    df_m = int(st.session_state["dias_manual_ffcc"])
                    dc_m = int(st.session_state["dias_manual_carr"])
                    if dp_m == 0 and df_m == 0 and dc_m == 0:
                        st.error("❌ Condonación manual activa: debes ingresar al menos 1 día en alguno de los campos. No hay condonaciones a realizar.")
                        st.session_state["paso"] = "inicio"
                        st.stop()
                    # Construir desfases manuales por contenedor
                    desfases = {}
                    for _, row in df_bv.iterrows():
                        cont   = row[COL_BI["contenedor"]]
                        dp_fin = 0 if perfil_act.get("na_previo", False) else dp_m
                        df_fin = 0 if perfil_act.get("na_ffcc", False)   else df_m
                        dc_fin = 0 if perfil_act.get("na_carretero", False) else dc_m
                        desfases[cont] = {
                            "desfase_previo":    dp_fin,
                            "desfase_ffcc":      df_fin,
                            "desfase_carretero": dc_fin,
                            "total_desfase":     dp_fin + df_fin + dc_fin,
                            "es_manual":         True,
                            "na_previo":         perfil_act.get("na_previo", False),
                            "na_ffcc":           perfil_act.get("na_ffcc", False),
                            "na_carretero":      perfil_act.get("na_carretero", False),
                        }
                else:
                    desfases = calcular_desfases(
                        df_bv, st.session_state["dias_especiales"], perfil
                    )
                    for cont in desfases:
                        desfases[cont]["es_manual"]    = False
                        desfases[cont]["na_previo"]    = perfil_act.get("na_previo", False)
                        desfases[cont]["na_ffcc"]      = perfil_act.get("na_ffcc", False)
                        desfases[cont]["na_carretero"] = perfil_act.get("na_carretero", False)
                        # Aplicar NA: poner 0 en los conceptos que no aplican
                        if desfases[cont]["na_previo"]:
                            desfases[cont]["desfase_previo"] = 0
                        if desfases[cont]["na_ffcc"]:
                            desfases[cont]["desfase_ffcc"] = 0
                        if desfases[cont]["na_carretero"]:
                            desfases[cont]["desfase_carretero"] = 0
                        desfases[cont]["total_desfase"] = (
                            desfases[cont]["desfase_previo"] +
                            desfases[cont]["desfase_ffcc"] +
                            desfases[cont]["desfase_carretero"]
                        )

            with st.spinner("Calculando montos..."):
                montos = calcular_montos(df_bv, desfases)

            # Regla 1
            no_r1 = aplicar_regla1(df_bv, df_tv, fecha_sol, {}, perfil)
            if no_r1:
                alertas.append(("warning",
                    f"**Regla 1 — 30 días:** Contenedores fuera de plazo: "
                    f"{', '.join(no_r1)}"))

            # Regla 2
            no_r2 = aplicar_regla2(df_bv, perfil)
            if no_r2:
                alertas.append(("warning",
                    f"**Regla 2 — 4 días:** Contenedores que no cumplen: "
                    f"{', '.join(no_r2)}"))

            # ── Comentario dinámico para condonación manual ───────
            if st.session_state["cond_manual"]:
                dp_m = int(st.session_state["dias_manual_previo"])
                df_m = int(st.session_state["dias_manual_ffcc"])
                dc_m = int(st.session_state["dias_manual_carr"])
                alertas.append(("info",
                    f"**Condonación Manual Directa activa:** "
                    f"Previo={dp_m} días | Ferroviario={df_m} días | "
                    f"Carretero={dc_m} días | Total={dp_m+df_m+dc_m} días"))

            # Alertas liner y reprogramaciones
            liners, reprog = [], []
            for _, row in df_bv.iterrows():
                cont = row[COL_BI["contenedor"]]
                fa2  = row.get(COL_BI["fecha_auth_naviera"])
                if pd.notna(fa2) and str(fa2).strip() not in ("","nan"):
                    liners.append(cont)
                try:
                    if int(row.get(COL_BI["no_entregas"], 0)) >= 2:
                        reprog.append(cont)
                except Exception:
                    pass

            if liners:
                alertas.append(("info",
                    f"**Liner:** Revisar autorización naviera para: "
                    f"{', '.join(liners)}"))
            if reprog:
                alertas.append(("warning",
                    f"**Reprogramaciones:** Más de 1 programación en: "
                    f"{', '.join(reprog)}"))

            st.session_state["df_tab_v"]        = df_tv
            st.session_state["df_bi_v"]         = df_bv
            st.session_state["desfases"]        = desfases
            st.session_state["montos"]          = montos
            st.session_state["fecha_solicitud"] = fecha_sol
            st.session_state["nc_cliente"]      = nc_input.strip()
            st.session_state["fecha_revision"]  = hoy_mx()
            st.session_state["alertas"]         = alertas

            # ── Detectar contenedores con 2+ servicios ───────────
            from app.config import COL_BI as _CB
            conts_multi = []
            for _, row in df_bv.iterrows():
                try:
                    ns = int(row.get(_CB.get("no_servicios","No. Servicios"), 0) or 0)
                    if ns >= 2:
                        conts_multi.append(row[_CB["contenedor"]])
                except Exception:
                    pass

            if conts_multi:
                st.session_state["conts_multi_previo"] = conts_multi
                st.session_state["paso"] = "previo_alerta"
            else:
                st.session_state["conts_multi_previo"] = []
                st.session_state["paso"] = "confirmacion"
            st.rerun()

        # ════════════════════════════════════════════════════
        #   FLUJO: ALERTA PREVIOS MÚLTIPLES
        # ════════════════════════════════════════════════════
        if st.session_state["paso"] == "previo_alerta":
            from app.config import COL_BI as _CB2
            conts = st.session_state.get("conts_multi_previo", [])
            nc    = st.session_state.get("nc_cliente", "")
            usr   = st.session_state["usuario"]
            tiene_borrador = hay_borrador_activo(usr["id"], nc)

            st.markdown("### Servicios múltiples de previo detectados")
            st.warning(
                "Se detectaron contenedor(es) con 2 o más servicios programados. "
                "Considerar que el BI únicamente maneja una sola fecha de previo desde "
                "la primera programación hasta el posicionamiento, aunque sea en un "
                "servicio distinto al primero. "
                "¿Deseas ajustar manualmente las fechas de previo de manera individual?"
            )
            if tiene_borrador:
                st.info("Se encontró un borrador guardado para esta NC. "
                        "Puedes continuar donde lo dejaste.")
            pa1, pa2 = st.columns(2)
            with pa1:
                if st.button("✅ Sí, ajustar manualmente", type="primary",
                             use_container_width=True, key="previo_si"):
                    st.session_state["paso"] = "previo_manual"
                    if "contadores_previo" not in st.session_state:
                        st.session_state["contadores_previo"] = {}
                    for c in conts:
                        if c not in st.session_state["contadores_previo"]:
                            st.session_state["contadores_previo"][c] = 1
                    st.rerun()
            with pa2:
                if st.button("No, continuar con cálculo automático",
                             use_container_width=True, key="previo_no"):
                    eliminar_borradores_nc(usr["id"], nc)
                    st.session_state["paso"] = "confirmacion"
                    st.rerun()

        # ════════════════════════════════════════════════════
        #   FLUJO: CAPTURA MANUAL DE PREVIOS
        # ════════════════════════════════════════════════════
        if st.session_state["paso"] == "previo_manual":
            from app.calendario import calcular_desfase_regla3 as _cdr3
            from app.validaciones import to_date as _td, calcular_montos as _cm
            from app.config import COL_BI as _CB3
            from datetime import datetime as _dt2

            nc      = st.session_state.get("nc_cliente", "")
            usr     = st.session_state["usuario"]
            perfil  = st.session_state["perfiles"][st.session_state["perfil_idx"]]
            conts   = st.session_state.get("conts_multi_previo", [])
            df_bv   = st.session_state["df_bi_v"]
            dias_esp = st.session_state["dias_especiales"]

            if "contadores_previo" not in st.session_state:
                st.session_state["contadores_previo"] = {c: 1 for c in conts}

            borradores = cargar_borradores_previo(usr["id"], nc)
            bor_dict   = {(b["contenedor"], b["previo_num"]): b for b in borradores}

            # Actualizar contadores según borradores
            for c in conts:
                max_num = max(
                    [b["previo_num"] for b in borradores if b["contenedor"] == c],
                    default=0
                )
                cur = st.session_state["contadores_previo"].get(c, 1)
                if max_num > cur:
                    st.session_state["contadores_previo"][c] = max_num

            st.markdown("### Captura manual de fechas de previo")
            st.caption("Los cambios se guardan automáticamente. "
                       "Puedes cerrar la app y continuar después.")

            completados = sum(
                1 for c in conts
                if any(b["contenedor"] == c and b.get("fecha_programacion")
                       and b.get("fecha_posicionamiento") for b in borradores)
            )
            total = len(conts)
            pct   = completados / total if total else 0
            st.progress(pct,
                text=f"{completados} de {total} contenedores completados — {int(pct*100)}%")
            st.markdown("---")

            for cont in conts:
                bors_cont  = [b for b in borradores if b["contenedor"] == cont]
                completado = (len(bors_cont) > 0 and
                              all(b.get("fecha_programacion") and
                                  b.get("fecha_posicionamiento") for b in bors_cont))
                n_previos  = st.session_state["contadores_previo"].get(cont, 1)

                ns_val = 0
                for _, row in df_bv.iterrows():
                    if row[_CB3["contenedor"]] == cont:
                        try: ns_val = int(row.get("No. Servicios", 0) or 0)
                        except: pass
                        break

                lbl = (f"✅ {cont}  ({ns_val} servicios) — Completado"
                       if completado else
                       f"⏳ {cont}  ({ns_val} servicios) — Pendiente")

                with st.expander(lbl, expanded=not completado):
                    def parse_fecha_bor(v):
                        """Convierte valor de BD a date de Python."""
                        if not v:
                            return None
                        try:
                            if hasattr(v, 'date'):
                                return v.date() if callable(v.date) else v
                            if isinstance(v, str):
                                return _dt2.strptime(v[:10], "%Y-%m-%d").date()
                        except:
                            pass
                        return None

                    for pnum in range(1, n_previos + 1):
                        bor = bor_dict.get((cont, pnum), {})

                        # Encabezado del previo con botón eliminar (solo si no es el 1)
                        ph1, ph2 = st.columns([4, 1])
                        with ph1:
                            st.markdown(f"**Previo {pnum}**")
                        with ph2:
                            if pnum > 1:
                                if st.button("🗑️ Eliminar",
                                             key=f"del_{cont}_{pnum}",
                                             use_container_width=True):
                                    # Eliminar de BD
                                    try:
                                        from app.database import get_client as _gc2
                                        _db = _gc2()
                                        _db.table("borradores_previo").delete(
                                        ).eq("usuario_id", usr["id"]
                                        ).eq("numero_nc", nc
                                        ).eq("contenedor", cont
                                        ).eq("previo_num", pnum).execute()
                                    except:
                                        pass
                                    # Reducir contador
                                    cur_n = st.session_state["contadores_previo"].get(cont, 1)
                                    if cur_n > 1:
                                        st.session_state["contadores_previo"][cont] = cur_n - 1
                                    st.rerun()

                        # Selectores de fecha (calendarios)
                        fc1, fc2 = st.columns(2)
                        with fc1:
                            prog_date = parse_fecha_bor(bor.get("fecha_programacion"))
                            prog = st.date_input(
                                "Fecha programación",
                                value=prog_date,
                                format="DD/MM/YYYY",
                                key=f"prog_{cont}_{pnum}"
                            )
                        with fc2:
                            pos_date = parse_fecha_bor(bor.get("fecha_posicionamiento"))
                            pos = st.date_input(
                                "Fecha posicionamiento",
                                value=pos_date,
                                format="DD/MM/YYYY",
                                key=f"pos_{cont}_{pnum}"
                            )

                        # Auto-guardar SOLO si el valor cambió (evita golpear la BD
                        # en cada rerun de Streamlit y que la app se sienta lenta)
                        if prog and pos:
                            try:
                                fp  = prog.strftime("%Y-%m-%d") if hasattr(prog, 'strftime') else str(prog)
                                fpo = pos.strftime("%Y-%m-%d")  if hasattr(pos,  'strftime') else str(pos)
                                previo_actual = (
                                    str(bor.get("fecha_programacion") or "")[:10],
                                    str(bor.get("fecha_posicionamiento") or "")[:10],
                                )
                                if (fp, fpo) != previo_actual:
                                    guardar_previo_borrador(usr["id"], nc, cont, pnum, fp, fpo)
                            except:
                                pass

                        if pnum < n_previos:
                            st.divider()

                    if n_previos < 50:
                        if st.button("＋ Agregar otro previo",
                                     key=f"add_{cont}"):
                            st.session_state["contadores_previo"][cont] = n_previos + 1
                            st.rerun()

            st.markdown("---")
            if st.button("💾 Calcular desfases y continuar",
                         type="primary", use_container_width=True,
                         key="calc_previos"):
                desfases = st.session_state["desfases"]
                dias_p   = perfil.get("dias_previo", 3)
                bors_fin = cargar_borradores_previo(usr["id"], nc)

                for cont in conts:
                    bors = sorted(
                        [b for b in bors_fin if b["contenedor"] == cont],
                        key=lambda x: x["previo_num"]
                    )
                    total_d = 0
                    for b in bors:
                        try:
                            fp  = _dt2.strptime(b["fecha_programacion"],  "%Y-%m-%d").date()
                            fpo = _dt2.strptime(b["fecha_posicionamiento"], "%Y-%m-%d").date()
                            d, _ = _cdr3(fp, fpo, dias_esp, dias_p)
                            total_d += d
                        except: pass

                    if cont in desfases:
                        desfases[cont]["desfase_previo"] = total_d
                        desfases[cont]["total_desfase"]  = (
                            total_d +
                            desfases[cont].get("desfase_ffcc", 0) +
                            desfases[cont].get("desfase_carretero", 0)
                        )

                st.session_state["desfases"] = desfases
                st.session_state["montos"]   = _cm(df_bv, desfases)
                st.session_state["paso"]     = "confirmacion"
                st.rerun()

        # ════════════════════════════════════════════════════
        #   FLUJO: CONFIRMACIÓN DE DESFASES
        # ════════════════════════════════════════════════════
        if st.session_state["paso"] == "confirmacion":
            desfases = st.session_state["desfases"]

            st.markdown("### Resumen de días de desfase detectados")
            resumen = [{"Contenedor": c,
                        "Previo":     d["desfase_previo"],
                        "FFCC":       d["desfase_ffcc"],
                        "Carretero":  d["desfase_carretero"],
                        "Total":      d["total_desfase"]}
                       for c, d in desfases.items()]
            st.dataframe(pd.DataFrame(resumen), use_container_width=True,
                         hide_index=True)

            st.markdown("**¿Estás de acuerdo con los días de desfase calculados?**")
            cc1, cc2 = st.columns(2)
            with cc1:
                if st.button("✅ Sí, generar reporte", type="primary",
                             use_container_width=True, key="btn_si"):
                    st.session_state["paso"] = "reporte"
                    st.rerun()
            with cc2:
                if st.button("✏️ No, ajustar manualmente",
                             use_container_width=True, key="btn_no"):
                    st.session_state["paso"] = "ajuste"
                    st.rerun()

        # ════════════════════════════════════════════════════
        #   FLUJO: AJUSTE MANUAL
        # ════════════════════════════════════════════════════
        if st.session_state["paso"] == "ajuste":
            desfases = st.session_state["desfases"]
            st.markdown("### Ajuste Manual de Días de Desfase")

            dias_global  = st.number_input("Días para TODOS los seleccionados",
                                            min_value=0, value=0)
            contenedores = list(desfases.keys())
            checks, entries = {}, {}

            for cont in contenedores:
                ac1, ac2, ac3 = st.columns([1,2,1])
                with ac1:
                    checks[cont] = st.checkbox(cont, value=True, key=f"chk_{cont}")
                with ac2:
                    st.caption(f"Calculado: {desfases[cont]['total_desfase']} días")
                with ac3:
                    if not checks[cont]:
                        entries[cont] = st.number_input(
                            "Días", min_value=0, value=0,
                            key=f"d_{cont}", label_visibility="collapsed"
                        )

            if st.button("💾 Guardar y generar reporte", type="primary",
                         use_container_width=True):
                for cont in contenedores:
                    if checks.get(cont, True):
                        desfases[cont]["total_desfase"] = int(dias_global)
                    else:
                        desfases[cont]["total_desfase"] = int(entries.get(cont, 0))
                st.session_state["desfases"] = desfases
                st.session_state["montos"]   = calcular_montos(
                    st.session_state["df_bi_v"], desfases
                )
                st.session_state["paso"] = "reporte"
                st.rerun()

        # ════════════════════════════════════════════════════
        #   FLUJO: GENERAR REPORTE
        # ════════════════════════════════════════════════════
        if st.session_state["paso"] == "reporte":
            df_tv     = st.session_state["df_tab_v"]
            df_bv     = st.session_state["df_bi_v"]
            desfases  = st.session_state["desfases"]
            montos    = st.session_state["montos"]
            fecha_sol = st.session_state["fecha_solicitud"]
            nc        = st.session_state["nc_cliente"]
            fecha_rev = st.session_state["fecha_revision"]

            # Alertas finales
            sin_alm = [row[COL_BI["contenedor"]]
                       for _, row in df_bv.iterrows()
                       if float(row.get(COL_BI["alm_qty"], 0) or 0) <= 0]
            if sin_alm:
                st.warning(f"Sin almacenajes cobrados para: {', '.join(sin_alm)}")

            admon_sin = [row[COL_BI["contenedor"]]
                         for _, row in df_bv.iterrows()
                         if float(row.get(COL_BI["alm_qty"], 0) or 0) <= 0
                         and float(row.get(COL_BI["admon_qty"], 0) or 0) > 0]
            if admon_sin:
                st.warning(f"Cobro Admin y Control sin almacenajes: "
                           f"{', '.join(admon_sin)}")

            with st.spinner("Generando reporte Excel..."):
                buffer = io.BytesIO()
                generar_reporte(df_tv, df_bv, desfases, montos,
                                fecha_sol, fecha_rev, nc, {}, buffer)
                buffer.seek(0)
                excel_bytes = buffer.getvalue()

            # ── Heredar Cliente y Factura hacia NC Asignada ─────
            cliente_val  = ""
            factura_val  = ""
            for _, row in df_bv.iterrows():
                if not cliente_val and row.get(COL_BI.get("cliente")):
                    cliente_val = str(row.get(COL_BI.get("cliente")))
                if not factura_val and row.get(COL_BI.get("no_factura")):
                    factura_val = str(row.get(COL_BI.get("no_factura")))
                if cliente_val and factura_val:
                    break

            nc_existente = next(
                (n for n in _cached_nc_asignaciones() if n["nc_externo"] == nc), None
            )
            if nc_existente:
                actualizar_herencia_analisis(nc_existente["id"], cliente_val, factura_val)
            else:
                # Crear registro huérfano para que el admin lo gestione
                ok_h, id_h = crear_nc_asignacion(
                    nc, usuario["id"], usuario["nombre_completo"],
                    fecha_sol.isoformat(), usuario["id"]
                )
                if ok_h:
                    actualizar_herencia_analisis(id_h, cliente_val, factura_val)

            # ── Registrar en BD al descargar ──────────────────
            if "nc_registrada" not in st.session_state:
                st.session_state["nc_registrada"] = False

            st.success("¡Reporte generado exitosamente!")

            def on_download():
                if not st.session_state["nc_registrada"]:
                    contenedores_list = df_bv[COL_BI["contenedor"]].tolist()
                    facturas_list = (df_bv[COL_BI["no_factura"]].tolist()
                                     if COL_BI["no_factura"] in df_bv.columns else [])
                    monto_total = sum(m.get("monto_total", 0)
                                      for m in montos.values())
                    registrar_nc(
                        numero_nc=nc,
                        usuario_id=usuario["id"],
                        usuario_nombre=nombre_user,
                        contenedores=contenedores_list,
                        facturas=facturas_list,
                        monto_total=monto_total
                    )
                    st.session_state["nc_registrada"] = True

            st.download_button(
                label="⬇️ Descargar Reporte Excel",
                data=excel_bytes,
                file_name=f"{nc or 'reporte'}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                on_click=on_download
            )

            st.markdown("---")
            if st.button("↺ Realizar nuevo análisis", use_container_width=True):
                st.session_state["df_tab"]             = None
                st.session_state["df_bi"]              = None
                st.session_state["df_tab_v"]           = None
                st.session_state["df_bi_v"]            = None
                st.session_state["desfases"]           = {}
                st.session_state["montos"]             = {}
                st.session_state["alertas"]            = []
                st.session_state["paso"]               = "inicio"
                st.session_state["uploader_key"]      += 1
                st.session_state["nc_registrada"]      = False
                st.session_state["cond_manual"]        = False
                st.session_state["dias_manual_previo"] = 0
                st.session_state["dias_manual_ffcc"]   = 0
                st.session_state["dias_manual_carr"]   = 0
                st.rerun()

    # ── Panel derecho: Calendario ─────────────────────────────
    with col_der:
        st.markdown("<div class='sec-hdr'>Días No Hábiles — Calendario</div>",
                    unsafe_allow_html=True)

        hoy      = hoy_mx()
        festivos = get_festivos_oficiales(st.session_state["cal_anio"])
        meses_es = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                    "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]

        cn1, cn2, cn3 = st.columns([1,3,1])
        with cn1:
            if st.button("‹", key="cant"):
                if st.session_state["cal_mes"] == 1:
                    st.session_state["cal_mes"]  = 12
                    st.session_state["cal_anio"] -= 1
                else:
                    st.session_state["cal_mes"] -= 1
                st.rerun()
        with cn2:
            st.markdown(f"**{meses_es[st.session_state['cal_mes']-1]} "
                        f"{st.session_state['cal_anio']}**")
        with cn3:
            if st.button("›", key="csig"):
                if st.session_state["cal_mes"] == 12:
                    st.session_state["cal_mes"]  = 1
                    st.session_state["cal_anio"] += 1
                else:
                    st.session_state["cal_mes"] += 1
                st.rerun()

        cal     = calendar.Calendar(firstweekday=0)
        semanas = cal.monthdayscalendar(st.session_state["cal_anio"],
                                         st.session_state["cal_mes"])
        dias_n  = ["Lu","Ma","Mi","Ju","Vi","Sa","Do"]
        hcols   = st.columns(7)
        for i, d in enumerate(dias_n):
            color = "#E65100" if i >= 5 else "#666"
            hcols[i].markdown(
                f"<div style='text-align:center;color:{color};"
                f"font-size:12px;font-weight:bold;'>{d}</div>",
                unsafe_allow_html=True
            )

        for semana in semanas:
            dcols = st.columns(7)
            for i, dia in enumerate(semana):
                if dia == 0:
                    dcols[i].write("")
                    continue
                fecha    = date(st.session_state["cal_anio"],
                                st.session_state["cal_mes"], dia)
                es_finde = i >= 5
                es_fest  = fecha in festivos
                es_esp   = fecha in st.session_state["dias_especiales"]
                es_hoy   = fecha == hoy

                if es_hoy:      bg = "🟦"
                elif es_esp:    bg = "🟨"
                elif es_fest:   bg = "🟧"
                elif es_finde:  bg = "⬜"
                else:           bg = "  "

                if dcols[i].button(f"{bg}{dia}", key=f"c_{fecha}",
                                    use_container_width=True):
                    if fecha in st.session_state["dias_especiales"]:
                        st.session_state["dias_especiales"].discard(fecha)
                    else:
                        st.session_state["dias_especiales"].add(fecha)
                    st.rerun()

        st.markdown("🟧 Festivo · 🟨 Especial · ⬜ Fin de semana · 🟦 Hoy")

        if st.session_state["dias_especiales"]:
            fechas_str = ", ".join(sorted(
                d.strftime("%d/%m/%Y")
                for d in st.session_state["dias_especiales"]
            ))
            st.caption(f"Días especiales: {fechas_str}")
        else:
            st.caption("Ningún día especial marcado")

        if st.button("🗑️ Limpiar días especiales"):
            st.session_state["dias_especiales"] = set()
            st.rerun()

# ════════════════════════════════════════════════════════════════
#   PESTAÑA 2 — HISTORIAL NC
# ════════════════════════════════════════════════════════════════
with nav[1]:
    st.markdown("<div class='sec-hdr'>Historial de Notas de Crédito</div>",
                unsafe_allow_html=True)

    with st.spinner("Cargando historial..."):
        historial_completo = obtener_historial(2000)

    if not historial_completo:
        st.info("No hay notas de crédito registradas aún.")
    else:
        # ── Filtros y búsqueda ────────────────────────────────
        sf1, sf2, sf3 = st.columns([2, 2, 2])
        with sf1:
            busqueda = st.text_input("🔍 Buscar por NC, contenedor o factura",
                                      placeholder="Ej: NC-2585 / MSCU1234567 / FAC-001",
                                      key="hist_busqueda")
        with sf2:
            usuarios_hist = sorted(set(r["usuario_nombre"] for r in historial_completo))
            filtro_usuario = st.selectbox("👤 Filtrar por usuario",
                                          ["Todos"] + usuarios_hist,
                                          key="hist_usuario")
        with sf3:
            col_f1, col_f2 = st.columns(2)
            fecha_desde = col_f1.date_input("Desde", value=None,
                                             key="hist_desde",
                                             format="DD/MM/YYYY")
            fecha_hasta = col_f2.date_input("Hasta", value=None,
                                             key="hist_hasta",
                                             format="DD/MM/YYYY")

        # ── Aplicar filtros ───────────────────────────────────
        historial = historial_completo.copy()

        if busqueda.strip():
            termino = busqueda.strip().upper()
            # Buscar por NC directo
            por_nc = [r for r in historial if termino in r["numero_nc"].upper()]
            ids_nc = {r["id"] for r in por_nc}

            # Buscar por contenedor o factura en detalle_nc
            try:
                from app.database import get_client as _gc
                db2 = _gc()
                res2 = db2.table("detalle_nc").select(
                    "historial_nc_id, contenedor, numero_factura"
                ).or_(
                    f"contenedor.ilike.%{termino}%,"
                    f"numero_factura.ilike.%{termino}%"
                ).execute()
                ids_detalle = {r["historial_nc_id"] for r in (res2.data or [])}
            except Exception:
                ids_detalle = set()

            ids_total = ids_nc | ids_detalle
            historial = [r for r in historial if r["id"] in ids_total]

        if filtro_usuario != "Todos":
            historial = [r for r in historial
                        if r["usuario_nombre"] == filtro_usuario]

        if fecha_desde:
            historial = [r for r in historial
                        if r["fecha_creacion"] and
                        r["fecha_creacion"][:10] >= fecha_desde.isoformat()]

        if fecha_hasta:
            historial = [r for r in historial
                        if r["fecha_creacion"] and
                        r["fecha_creacion"][:10] <= fecha_hasta.isoformat()]

        # ── Paginación ────────────────────────────────────────
        REGISTROS_POR_PAG = 20
        total_regs  = len(historial)
        total_pags  = max(1, -(-total_regs // REGISTROS_POR_PAG))  # ceil division

        if "hist_pag" not in st.session_state:
            st.session_state["hist_pag"] = 1

        # Reset página si cambió el filtro
        if st.session_state.get("hist_filtro_prev") != (busqueda, filtro_usuario, fecha_desde, fecha_hasta):
            st.session_state["hist_pag"] = 1
            st.session_state["hist_filtro_prev"] = (busqueda, filtro_usuario, fecha_desde, fecha_hasta)

        pag_actual = st.session_state["hist_pag"]

        # Controles de paginación arriba
        pc1, pc2, pc3 = st.columns([1, 3, 1])
        with pc1:
            if st.button("◀ Anterior", disabled=pag_actual <= 1, key="pag_ant"):
                st.session_state["hist_pag"] -= 1
                st.rerun()
        with pc2:
            inicio = (pag_actual - 1) * REGISTROS_POR_PAG + 1
            fin    = min(pag_actual * REGISTROS_POR_PAG, total_regs)
            st.markdown(f"<div style='text-align:center;padding:6px;font-size:13px;'>"
                        f"Mostrando <b>{inicio}–{fin}</b> de <b>{total_regs}</b> registros "
                        f"— Página <b>{pag_actual}</b> de <b>{total_pags}</b></div>",
                        unsafe_allow_html=True)
        with pc3:
            if st.button("Siguiente ▶", disabled=pag_actual >= total_pags, key="pag_sig"):
                st.session_state["hist_pag"] += 1
                st.rerun()

        st.markdown("---")

        # ── Registros de la página actual ─────────────────────
        idx_inicio = (pag_actual - 1) * REGISTROS_POR_PAG
        idx_fin    = idx_inicio + REGISTROS_POR_PAG
        pag_regs   = historial[idx_inicio:idx_fin]

        if not pag_regs:
            st.info("No se encontraron registros con los filtros aplicados.")
        else:
            for reg in pag_regs:
                fecha_str = reg["fecha_creacion"][:10] if reg["fecha_creacion"] else "—"
                monto_str = f"${reg['monto_total']:,.2f}" if reg["monto_total"] else "$0.00"

                with st.expander(
                    f"📄 {reg['numero_nc']}  —  {fecha_str}  —  {reg['usuario_nombre']}  —  {monto_str}"
                ):
                    col_info, col_acc = st.columns([3, 1])
                    with col_info:
                        st.write(f"**Fecha:** {fecha_str}")
                        st.write(f"**Usuario:** {reg['usuario_nombre']}")
                        st.write(f"**Contenedores:** {reg['total_contenedores']}")
                        st.write(f"**Monto Total:** {monto_str}")

                        if st.button("🔍 Ver Detalle", key=f"det_{reg['id']}"):
                            with st.spinner("Cargando detalle..."):
                                detalle = obtener_detalle_nc(reg["id"])
                            if detalle:
                                df_det = pd.DataFrame(detalle)
                                df_det.columns = ["Contenedor", "N° Factura"]
                                st.dataframe(df_det, use_container_width=True,
                                             hide_index=True)
                            else:
                                st.info("Sin detalle disponible.")

                    with col_acc:
                        if es_admin:
                            if st.button("🗑️ Eliminar", key=f"del_{reg['id']}",
                                         type="secondary"):
                                if eliminar_nc(reg["id"]):
                                    st.success("Registro eliminado")
                                    st.rerun()
                                else:
                                    st.error("Error al eliminar")

        # Controles de paginación abajo también
        st.markdown("---")
        pb1, pb2, pb3 = st.columns([1, 3, 1])
        with pb1:
            if st.button("◀ Anterior", disabled=pag_actual <= 1, key="pag_ant2"):
                st.session_state["hist_pag"] -= 1
                st.rerun()
        with pb2:
            st.markdown(f"<div style='text-align:center;padding:6px;font-size:13px;'>"
                        f"Página <b>{pag_actual}</b> de <b>{total_pags}</b></div>",
                        unsafe_allow_html=True)
        with pb3:
            if st.button("Siguiente ▶", disabled=pag_actual >= total_pags, key="pag_sig2"):
                st.session_state["hist_pag"] += 1
                st.rerun()

# ════════════════════════════════════════════════════════════════
#   PESTAÑA 3 — USUARIOS (solo admin)
# ════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════
#   PESTAÑA 3 — REGLAS DE APLICACIÓN
# ════════════════════════════════════════════════════════════════
tab_reglas_idx = 2
with nav[tab_reglas_idx]:
    st.markdown("<div class='sec-hdr'>📖 Reglas de Aplicación del Sistema</div>",
                unsafe_allow_html=True)

    st.markdown("""
    <div style='background:#FFF3E0;border-left:4px solid #E65100;padding:12px 16px;
                border-radius:6px;margin-bottom:16px;font-size:14px;'>
    ℹ️ Esta sección es <b>informativa</b>. Describe cómo el sistema calcula las condonaciones
    y qué datos se requieren de los archivos Excel para que el análisis sea correcto.
    </div>
    """, unsafe_allow_html=True)

    with st.expander("📁 Archivos requeridos", expanded=True):
        st.markdown("""
        El sistema requiere **2 archivos Excel** para realizar el análisis:

        **📋 Tabulador Comercial** — Llenado por el cliente. Se usan:
        - `CONTENEDOR` — Identificador único del contenedor
        - `IMPORTE SIN IVA A CONDONAR` — Monto solicitado por el cliente
        - `CLABE INTERBANCARIA` — Datos bancarios para la devolución

        **📊 Archivo BI** — Descargado del sistema interno. Contiene fechas, montos y servicios por contenedor.
        Ambos archivos deben tener **exactamente los mismos contenedores**.
        El formato del contenedor debe ser: **4 letras + 7 números** (ejemplo: MSCU1234567).
        """)

    with st.expander("📅 Regla 1 — Plazo de 30 días naturales"):
        st.markdown("""
        ⏱️ **¿Qué valida?**
        La solicitud de condonación debe realizarse dentro de los **30 días naturales**
        posteriores a la fecha de salida del contenedor.

        📌 **Datos utilizados:**
        - `TimeOut` → Fecha real de salida del contenedor
        - `Fecha de Solicitud NC` → Fecha ingresada por el usuario en la interfaz

        ✅ **Si cumple:** Continúa el análisis normalmente.
        ⚠️ **Si no cumple:** Se muestra alerta con los contenedores fuera de plazo.
        El usuario decide si continúa o cancela.

        💡 **Este parámetro puede desactivarse en perfiles personalizados.**
        """)

    with st.expander("📅 Regla 2 — Primeros 4 días desde ingreso"):
        st.markdown("""
        ⏱️ **¿Qué valida?**
        La primera programación del cliente debe realizarse dentro de los **primeros 4 días naturales**
        desde que el contenedor ingresó a la terminal. El día de ingreso cuenta como Día 1.

        📌 **Datos utilizados:**
        - `TimeIn` → Fecha de ingreso (Día 1, sin importar la hora)
        - `FechaSolitudPrevio` → Fecha de solicitud de previo (opcional)
        - `Fecha de Liberacion` → Fecha de solicitud de liberación

        ✅ **Basta con que UNA de las dos fechas esté dentro del plazo.**
        Si `FechaSolitudPrevio` está vacío, solo se valida con Liberación.

        💡 **Este parámetro puede desactivarse en perfiles personalizados.**
        """)

    with st.expander("🔄 Regla 3 — Posicionamiento de Previo (días hábiles Lun–Sáb)"):
        st.markdown("""
        ⏱️ **¿Qué calcula?**
        La terminal tiene un máximo de **3 días hábiles** (por default) a partir del día
        siguiente a la solicitud de previo para posicionar el contenedor.

        📌 **Datos utilizados:**
        - `FechaSolitudPrevio` → Inicio del conteo
        - `FechaPosicionamiento` → Fecha real de posicionamiento

        📋 **Días que NO cuentan dentro del plazo:**
        - Domingos siempre
        - Festivos oficiales de México
        - Días marcados manualmente en el calendario

        ⚠️ **Si el campo está vacío**, el servicio no fue solicitado. Se registra 0 días de desfase.
        💡 **El número de días puede modificarse en perfiles personalizados.**
        """)

    with st.expander("🚂 Regla 4 — Carga a Góndola FFCC (días naturales)"):
        st.markdown("""
        ⏱️ **¿Qué calcula?**
        Para contenedores con **salida ferroviaria**, la terminal tiene **3 días naturales**
        (por default) desde el día siguiente a la documentación ante FerroMex para cargar
        el contenedor a la góndola.

        📌 **Datos utilizados:**
        - `FechaFerroMex` → Fecha de documentación ante FerroMex
        - `Fecha Gondola` → Fecha real de carga a góndola

        ⚠️ **Importante:** Esta regla usa **días naturales**. No se aplican excepciones
        de fines de semana, festivos ni días del calendario.

        Si alguno de los dos campos está vacío, el contenedor tuvo otra modalidad de salida
        y esta regla no aplica (0 días de desfase).

        💡 **El número de días puede modificarse en perfiles personalizados.**
        """)

    with st.expander("🚚 Regla 5 — Entrega Carretero (días hábiles con excepciones)"):
        st.markdown("""
        ⏱️ **¿Qué calcula?**
        Para contenedores con **salida en camión**, la terminal tiene **2 días hábiles**
        (por default) desde el día siguiente a la programación de entrega.

        📌 **Datos utilizados:**
        - `Fecha de programación de entrega` → Inicio del conteo
        - `TimeOut` → Fecha real de entrega

        📋 **Reglas especiales del sábado:**
        - Si programó **Lunes a Miércoles** → el sábado SÍ cuenta como día hábil
        - Si programó **Jueves o Viernes** → el sábado NO cuenta en el plazo

        📋 **El domingo** nunca cuenta dentro del plazo, pero sí cuenta como día
        de desfase si el plazo ya venció.

        📋 **Festivos y días del calendario** solo se saltan si están dentro del plazo.
        Una vez que hay desfase, todos los días cuentan.

        💡 **El número de días puede modificarse en perfiles personalizados.**
        """)

    with st.expander("➕ Regla 6 — Total de Días de Desfase"):
        st.markdown("""
        **Fórmula:**
        ```
        Total Desfase = Días Regla 3 (Previo) + Días Regla 4 (FFCC) + Días Regla 5 (Carretero)
        ```
        Si alguna regla no aplica para un contenedor, se suma 0.
        Este total se usa para calcular los montos a condonar en las Reglas 7, 8 y 9.
        """)

    with st.expander("💰 Regla 7 — Monto a Condonar por Almacenaje"):
        st.markdown("""
        📌 **Datos del BI utilizados:**
        - `Almacenaje Qty` → Días totales de almacenaje cobrados
        - `Almacenaje SubTotal` → Monto total cobrado por almacenaje

        **Cálculo:**
        ```
        Costo por día = Almacenaje SubTotal ÷ Almacenaje Qty
        Días a condonar = MIN(Total Desfase, Almacenaje Qty)
        Monto a condonar = Costo por día × Días a condonar
        Días a cobrar = MAX(Almacenaje Qty - Días Desfase, 0)
        ```
        ⚠️ Los días de desfase nunca pueden superar los días totales cobrados.
        Si supera, se ecualiza automáticamente al máximo cobrado.
        """)

    with st.expander("❄️ Regla 8 — Monto a Condonar por Conexiones (Refrigerados)"):
        st.markdown("""
        Solo aplica para **contenedores refrigerados** con cobro de suministro de energía.
        Usa los mismos días de desfase de la Regla 6.

        📌 **Datos del BI utilizados:**
        - `Suministro De Energía Qty` → Días de conexión cobrados
        - `Suministro De Energía SubTotal` → Monto total cobrado

        **Cálculo:**
        ```
        Costo por día = Energía SubTotal ÷ Energía Qty
        Monto a condonar = Costo por día × MIN(Total Desfase, Energía Qty)
        ```
        Si los campos están vacíos o en 0, se registra **"No aplica"**.
        """)

    with st.expander("🏢 Regla 9 — Servicio de Administración y Control"):
        st.markdown("""
        Este servicio se condona de manera **total o nada** (sin condonaciones parciales).

        ✅ **Se condona si:**
        - Se cobró el servicio en la factura, Y
        - Los días de desfase cubren completamente los días de almacenaje cobrados

        ❌ **No se condona si:**
        - No se cobró el servicio, O
        - Los días de desfase son menores a los días de almacenaje totales

        📌 **Dato del BI:** `Servicio de Administración y Control SubTotal`
        """)

    with st.expander("✏️ Condonación Manual Directa"):
        st.markdown("""
        Esta opción permite **omitir el cálculo automático** de las Reglas 3, 4 y 5
        y colocar directamente los días a condonar por cada concepto.

        📋 **¿Cuándo usarla?**
        Cuando el cliente y la terminal acuerdan una cantidad específica de días
        a condonar sin pasar por las reglas de negocio estándar.

        📋 **¿Cómo funciona?**
        - Se ingresan los días manualmente para Previo, Ferroviario y Carretero
        - El total se usa igual que el resultado de la Regla 6
        - Se aplican las mismas restricciones: no se puede condonar más días
          de los que se cobraron en almacenaje
        - Al menos uno de los tres campos debe ser mayor a 0

        ⚠️ Las **Reglas 1 y 2** siguen validándose aunque la condonación sea manual.
        """)

    with st.expander("📆 Calendario de Días No Hábiles"):
        st.markdown("""
        El calendario permite marcar días que no se contarán como hábiles
        en el cálculo de los plazos de las **Reglas 3 y 5**.

        🟧 **Festivos oficiales** → Precargados automáticamente (Ley Federal del Trabajo)
        🟨 **Días especiales** → Marcados manualmente por el usuario (cierres de aduana, etc.)
        ⬜ **Fines de semana** → Sábados y domingos (efecto varía por regla)

        ⚠️ **Importante:** La **Regla 4 (FFCC)** usa días naturales y NO respeta
        el calendario ni festivos.

        Los días marcados solo afectan el plazo si caen **dentro del período de condonación**.
        Si el plazo ya venció y hay desfase, todos los días cuentan incluyendo los marcados.
        """)

# ════════════════════════════════════════════════════════════════
#   PESTAÑA UNIFICADA: GESTIÓN NC (con sub-pestañas)
# ════════════════════════════════════════════════════════════════
with nav[IDX_GESTION]:
    st.markdown("<div class='sec-hdr'>🗂️ Gestión de Notas de Crédito</div>",
                unsafe_allow_html=True)

    _sub_labels = []
    if es_admin:
        _sub_labels.append("➕ Asignar NC")
    _sub_labels += ["📌 NC Asignadas", "✅ NC Concluidas", "🗃️ NC Creadas"]
    sub_nav = st.tabs(_sub_labels)

    _si = 0
    if es_admin:
        with sub_nav[_si]:
            st.markdown("<div class='admin-hdr'>🗂️ Asignar Nota de Crédito</div>",
                        unsafe_allow_html=True)

            with st.expander("➕ Crear nueva NC", expanded=False):
                with st.form("form_nueva_nc"):
                    nc_ext = st.text_input("Número de nota de crédito externa")

                    usuarios_lista = _cached_usuarios()
                    nombres_usr = [u["nombre_completo"] for u in usuarios_lista if u["activo"]]
                    resp_sel = st.selectbox("Encargado responsable de la NC", nombres_usr)

                    fecha_sol_nc = st.date_input("Fecha de solicitud de NC",
                                                  value=hoy_mx(), format="DD/MM/YYYY")

                    vincular = st.checkbox("🔗 Vincular NC anterior")
                    nc_vinc_id = None
                    if vincular:
                        todas_nc = _cached_nc_asignaciones()
                        opciones_vinc = {f"{nc['nc_externo']} ({nc['id'][:8]})": nc["id"]
                                         for nc in todas_nc}
                        busq_vinc = st.text_input("Buscar NC para vincular")
                        filtradas = {k: v for k, v in opciones_vinc.items()
                                     if busq_vinc.upper() in k.upper()} if busq_vinc else opciones_vinc
                        if filtradas:
                            sel_vinc = st.selectbox("Selecciona la NC anterior", list(filtradas.keys()))
                            nc_vinc_id = filtradas.get(sel_vinc)
                        else:
                            st.caption("Sin coincidencias")

                    if st.form_submit_button("Crear NC", type="primary"):
                        if not nc_ext or not resp_sel:
                            st.warning("Completa todos los campos obligatorios")
                        else:
                            resp_obj = next((u for u in usuarios_lista
                                              if u["nombre_completo"] == resp_sel), None)
                            ok, res = crear_nc_asignacion(
                                nc_ext, resp_obj["id"], resp_obj["nombre_completo"],
                                fecha_sol_nc.isoformat(), usuario["id"], nc_vinc_id
                            )
                            if ok:
                                st.success(f"NC {nc_ext} creada y asignada a {resp_sel}")
                                invalidar_cache_nc()
                                st.rerun()
                            else:
                                st.error(f"Error: {res}")

            st.markdown("### Todas las NCs asignadas")
            busq_asig = st.text_input("🔍 Buscar por NC, contenedor o factura", key="busq_asignar")
            todas = buscar_nc_asignaciones(busq_asig) if busq_asig.strip() else _cached_nc_asignaciones()

            COLOR_VISUAL = {
                "nuevo":        ("🔵", "#E3F2FD"),
                "seguimiento":  ("🟢", "#E8F5E9"),
                "reasignado":   ("🟡", "#FFFDE7"),
            }

            for nc in todas:
                vis = nc.get("estado_visual", "nuevo")
                icono, bg = COLOR_VISUAL.get(vis, ("⚪", "#F5F5F5"))
                inhab = " ⛔ INHABILITADA" if nc.get("inhabilitada") else ""
                vinc_txt = ""
                if nc.get("vinculada_a"):
                    nc_padre = obtener_nc_por_id(nc["vinculada_a"])
                    if nc_padre:
                        vinc_txt = f" 🔗 vinculada con {nc_padre['nc_externo']}"

                with st.expander(f"{icono} {nc['nc_externo']} — {nc['responsable_nombre']} "
                                 f"— {nc['estatus']}{inhab}{vinc_txt}"):
                    st.write(f"**NC Externo:** {nc['nc_externo']}")
                    st.write(f"**NC Interno:** {nc.get('nc_interno') or '—'}")
                    st.write(f"**Responsable actual:** {nc['responsable_nombre']}")
                    st.write(f"**Fecha solicitud:** {nc.get('fecha_solicitud', '—')}")
                    st.write(f"**Estatus:** {nc['estatus']}")
                    if nc.get("cliente"):
                        st.write(f"**Cliente:** {nc['cliente']}")
                    if nc.get("numero_factura"):
                        st.write(f"**Factura:** {nc['numero_factura']}")

                    ra1, ra2 = st.columns(2)
                    with ra1:
                        nuevos_resp = [u["nombre_completo"] for u in usuarios_lista if u["activo"]]
                        idx_actual = (nuevos_resp.index(nc["responsable_nombre"])
                                      if nc["responsable_nombre"] in nuevos_resp else 0)
                        nuevo_resp_sel = st.selectbox(
                            "Reasignar a:", nuevos_resp, index=idx_actual,
                            key=f"reasig_{nc['id']}"
                        )
                        if nuevo_resp_sel != nc["responsable_nombre"]:
                            if st.button("Confirmar reasignación", key=f"btn_reasig_{nc['id']}"):
                                nuevo_obj = next((u for u in usuarios_lista
                                                  if u["nombre_completo"] == nuevo_resp_sel), None)
                                reasignar_nc(nc["id"], nuevo_obj["id"], nuevo_obj["nombre_completo"])
                                st.success("Reasignado correctamente")
                                invalidar_cache_nc()
                                st.rerun()
                    with ra2:
                        if not nc.get("inhabilitada"):
                            with st.popover("⛔ Inhabilitar NC"):
                                motivo_inhab = st.text_area("Motivo", key=f"motinhab_{nc['id']}")
                                if st.button("Confirmar inhabilitar", key=f"btninhab_{nc['id']}"):
                                    if motivo_inhab.strip():
                                        inhabilitar_nc(nc["id"], motivo_inhab.strip())
                                        st.success("NC inhabilitada")
                                        invalidar_cache_nc()
                                        st.rerun()
                                    else:
                                        st.warning("Escribe un motivo")
        _si += 1

    with sub_nav[_si]:
        st.markdown("<div class='sec-hdr'>📌 NC Asignadas</div>", unsafe_allow_html=True)

        if es_admin:
            lista_nc = [n for n in _cached_nc_asignaciones() if not n.get("concluida")]
        else:
            lista_nc = [n for n in obtener_nc_asignaciones(responsable_id=usuario["id"])
                        if not n.get("concluida")]

        motivos_disp = [m["texto"] for m in _cached_nc_motivos()]
        estatus_disp = [e["texto"] for e in _cached_nc_estatus()]
        estatus_concluido_set = {e["texto"] for e in _cached_nc_estatus() if e.get("es_concluido")}

        if not lista_nc:
            st.info("No tienes NCs asignadas pendientes.")

        for nc in lista_nc:
            vis = nc.get("estado_visual", "nuevo")
            icono = {"nuevo": "🔵", "seguimiento": "🟢", "reasignado": "🟡"}.get(vis, "⚪")
            inhab = " ⛔" if nc.get("inhabilitada") else ""

            with st.expander(f"{icono} {nc['nc_externo']} — {nc['estatus']}{inhab}",
                             expanded=False):
                marcar_seguimiento_nc(nc["id"])

                st.markdown("**Información fija (no editable):**")
                fi1, fi2, fi3 = st.columns(3)
                fi1.text_input("Fecha que se subió", value=str(nc.get("fecha_creacion",""))[:10],
                               disabled=True, key=f"ffija1_{nc['id']}")
                fi2.text_input("NC Externo", value=nc["nc_externo"], disabled=True,
                               key=f"ffija2_{nc['id']}")
                fi3.text_input("Responsable", value=nc["responsable_nombre"], disabled=True,
                               key=f"ffija3_{nc['id']}")

                if nc.get("cliente") or nc.get("numero_factura"):
                    st.caption(f"Cliente: {nc.get('cliente','—')}  |  "
                              f"Factura: {nc.get('numero_factura','—')}")

                st.markdown("---")
                st.markdown("**Información a completar:**")

                nc_int = st.text_input("NC Interno", value=nc.get("nc_interno") or "",
                                       key=f"ncint_{nc['id']}")

                idx_mot = (motivos_disp.index(nc["motivo"])
                           if nc.get("motivo") in motivos_disp else 0) if motivos_disp else 0
                motivo_sel = st.selectbox("Motivo de la solicitud de NC",
                                          motivos_disp if motivos_disp else ["—"],
                                          index=idx_mot, key=f"motivo_{nc['id']}")

                idx_est = (estatus_disp.index(nc["estatus"])
                           if nc.get("estatus") in estatus_disp else 0) if estatus_disp else 0
                estatus_sel = st.selectbox("Estatus de la NC",
                                           estatus_disp if estatus_disp else ["—"],
                                           index=idx_est, key=f"estatus_{nc['id']}")

                nc_emitida = ""
                if estatus_sel in estatus_concluido_set or "PENDIENTE POR EMITIR" in estatus_sel:
                    nc_emitida = st.text_input("Número de NC emitida",
                                               value=nc.get("numero_nc_emitida") or "",
                                               key=f"ncemit_{nc['id']}")

                st.markdown("**Contenedores** (pega el texto, se detectan automáticamente)")
                conts_texto = st.text_area("Pegar contenedores",
                                           value=nc.get("contenedores") or "",
                                           key=f"contstxt_{nc['id']}", height=80)
                conts_extraidos = extraer_contenedores(conts_texto) if conts_texto else \
                                  (nc.get("contenedores") or "").split(",")
                conts_extraidos = [c.strip() for c in conts_extraidos if c.strip()]

                if conts_extraidos:
                    st.caption(f"{len(conts_extraidos)} contenedor(es) detectado(s)")
                    st.dataframe(pd.DataFrame({"Contenedor": conts_extraidos}),
                                use_container_width=True, hide_index=True, height=150)

                comentarios_nc = st.text_area("Comentarios de la NC",
                                              value=nc.get("comentarios") or "",
                                              key=f"coment_{nc['id']}")

                if st.button("💾 Guardar información", type="primary",
                            key=f"guardar_nc_{nc['id']}"):
                    # Verificar duplicados de contenedores contra otras NC
                    dups = verificar_contenedores_en_nc(conts_extraidos, excluir_nc_id=nc["id"])
                    if dups:
                        st.session_state[f"dups_pendientes_{nc['id']}"] = dups
                        st.rerun()
                    else:
                        datos_guardar = {
                            "nc_interno":   nc_int,
                            "motivo":       motivo_sel,
                            "estatus":      estatus_sel,
                            "contenedores": ", ".join(conts_extraidos),
                            "comentarios":  comentarios_nc,
                        }
                        if nc_emitida:
                            datos_guardar["numero_nc_emitida"] = nc_emitida
                        if estatus_sel in estatus_concluido_set and nc_emitida:
                            datos_guardar["concluida"] = True
                        actualizar_nc_asignacion(nc["id"], datos_guardar)
                        invalidar_cache_nc()
                        st.success("Información guardada")
                        st.rerun()

                # Mostrar alertas de duplicados pendientes de decisión
                if st.session_state.get(f"dups_pendientes_{nc['id']}"):
                    dups = st.session_state[f"dups_pendientes_{nc['id']}"]
                    for dup in dups:
                        if not dup["concluida"]:
                            st.warning(
                                f"⚠️ El contenedor **{dup['contenedor']}** ya se encuentra en "
                                f"la solicitud **{dup['nc_externo']}**, vigente y asignada a "
                                f"**{dup['responsable_nombre']}**. Favor validar si no hay "
                                f"duplicidad. ¿Solicitud duplicada?"
                            )
                        else:
                            st.warning(
                                f"⚠️ Los contenedores de la solicitud ya se encuentran en una "
                                f"NC **finalizada**: **{dup['nc_externo']}**. "
                                f"¿Solicitud duplicada?"
                            )
                        dd1, dd2 = st.columns(2)
                        with dd1:
                            if st.button(f"Sí, es duplicada de {dup['nc_externo']}",
                                        key=f"dupsi_{nc['id']}_{dup['contenedor']}"):
                                inhabilitar_nc(nc["id"],
                                    f"Solicitud duplicada con la {dup['nc_externo']}")
                                del st.session_state[f"dups_pendientes_{nc['id']}"]
                                st.success("NC marcada como duplicada e inhabilitada")
                                invalidar_cache_nc()
                                st.rerun()
                        with dd2:
                            if st.button("No, continuar normalmente",
                                        key=f"dupno_{nc['id']}_{dup['contenedor']}"):
                                registrar_duplicado_revisado(
                                    nc["id"], dup["contenedor"], usuario["nombre_completo"]
                                )
                                datos_guardar = {
                                    "nc_interno":   nc_int,
                                    "motivo":       motivo_sel,
                                    "estatus":      estatus_sel,
                                    "contenedores": ", ".join(conts_extraidos),
                                    "comentarios":  comentarios_nc,
                                }
                                if nc_emitida:
                                    datos_guardar["numero_nc_emitida"] = nc_emitida
                                if estatus_sel in estatus_concluido_set and nc_emitida:
                                    datos_guardar["concluida"] = True
                                actualizar_nc_asignacion(nc["id"], datos_guardar)
                                del st.session_state[f"dups_pendientes_{nc['id']}"]
                                st.success("🔍 Revisado — información guardada")
                                invalidar_cache_nc()
                                st.rerun()
    _si += 1

    with sub_nav[_si]:
        st.markdown("<div class='sec-hdr'>✅ NC Concluidas</div>", unsafe_allow_html=True)

        concluidas = [n for n in _cached_nc_asignaciones() if n.get("concluida")]
        if not es_admin:
            concluidas = [n for n in concluidas if n["responsable_id"] == usuario["id"]]

        if not concluidas:
            st.info("No hay NCs concluidas.")

        for nc in concluidas:
            with st.expander(f"✅ {nc['nc_externo']} — {nc.get('numero_nc_emitida','—')} "
                             f"— {nc['responsable_nombre']}"):
                st.write(f"**NC Externo:** {nc['nc_externo']}")
                st.write(f"**NC Interno:** {nc.get('nc_interno') or '—'}")
                st.write(f"**NC Emitida:** {nc.get('numero_nc_emitida') or '—'}")
                st.write(f"**Responsable:** {nc['responsable_nombre']}")
                st.write(f"**Motivo:** {nc.get('motivo') or '—'}")
                st.write(f"**Estatus:** {nc['estatus']}")
                if nc.get("comentarios"):
                    st.write(f"**Comentarios:** {nc['comentarios']}")
                if nc.get("contenedores"):
                    conts_c = [c.strip() for c in nc["contenedores"].split(",") if c.strip()]
                    st.dataframe(pd.DataFrame({"Contenedor": conts_c}),
                                use_container_width=True, hide_index=True)

                if es_admin:
                    if st.button("↩️ Reabrir y regresar a NC Asignadas",
                                key=f"reabrir_{nc['id']}"):
                        reabrir_nc(nc["id"])
                        st.success("NC reabierta")
                        invalidar_cache_nc()
                        st.rerun()
    _si += 1

    with sub_nav[_si]:
        st.markdown("<div class='sec-hdr'>🗃️ NC Creadas</div>", unsafe_allow_html=True)
        st.caption("Vista de solo lectura — consulta el estatus de cualquier NC en el sistema.")

        busq_creadas = st.text_input("🔍 Buscar por NC, contenedor o factura", key="busq_creadas")
        todas_creadas = (buscar_nc_asignaciones(busq_creadas)
                         if busq_creadas.strip() else _cached_nc_asignaciones())

        if todas_creadas:
            tabla_creadas = []
            for nc in todas_creadas:
                tabla_creadas.append({
                    "NC Interno":  nc.get("nc_interno") or "—",
                    "NC Externo":  nc["nc_externo"],
                    "Contenedores": (nc.get("contenedores") or "")[:60],
                    "Estatus":     nc["estatus"],
                    "Comentarios": (nc.get("comentarios") or "")[:60],
                    "Responsable": nc["responsable_nombre"],
                })
            st.dataframe(pd.DataFrame(tabla_creadas), use_container_width=True, hide_index=True)
        else:
            st.info("No se encontraron NCs.")

if es_admin and IDX_USUARIOS is not None:
    with nav[IDX_USUARIOS]:
        st.markdown("<div class='admin-hdr'>Gestión de Usuarios</div>",
                    unsafe_allow_html=True)

        # ── Crear nuevo usuario ───────────────────────────────
        with st.expander("➕ Crear nuevo usuario", expanded=False):
            with st.form("form_nuevo_usuario"):
                cu1, cu2 = st.columns(2)
                nuevo_username = cu1.text_input("Usuario")
                nuevo_nombre   = cu2.text_input("Nombre completo")
                cu3, cu4 = st.columns(2)
                nuevo_pwd  = cu3.text_input("Contraseña", type="password")
                nuevo_pwd2 = cu4.text_input("Confirmar contraseña", type="password")
                nuevo_rol  = st.selectbox("Rol", ["usuario", "admin"])

                if st.form_submit_button("Crear usuario", type="primary"):
                    if not all([nuevo_username, nuevo_nombre, nuevo_pwd, nuevo_pwd2]):
                        st.warning("Completa todos los campos")
                    elif nuevo_pwd != nuevo_pwd2:
                        st.error("Las contraseñas no coinciden")
                    elif len(nuevo_pwd) < 6:
                        st.error("La contraseña debe tener al menos 6 caracteres")
                    else:
                        ok, msg = crear_usuario(nuevo_username, nuevo_pwd,
                                                nuevo_nombre, nuevo_rol)
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

        # ── Lista de usuarios ─────────────────────────────────
        st.markdown("### Usuarios registrados")
        with st.spinner("Cargando usuarios..."):
            usuarios = _cached_usuarios()

        for u in usuarios:
            es_yo = u["id"] == usuario["id"]
            fecha_u = u["fecha_creacion"][:10] if u["fecha_creacion"] else "—"
            badge   = "🔴 Admin" if u["rol"] == "admin" else "🔵 Usuario"
            estado  = "✅ Activo" if u["activo"] else "⛔ Inactivo"

            with st.expander(f"{badge} — {u['nombre_completo']} (@{u['username']}) — {estado}"):
                st.write(f"**Creado:** {fecha_u}")
                st.write(f"**Rol:** {u['rol'].capitalize()}")

                ua1, ua2, ua3 = st.columns(3)

                # Cambiar contraseña
                with ua1:
                    with st.popover("🔑 Cambiar contraseña"):
                        np1 = st.text_input("Nueva contraseña", type="password",
                                             key=f"np1_{u['id']}")
                        np2 = st.text_input("Confirmar", type="password",
                                             key=f"np2_{u['id']}")
                        if st.button("Guardar", key=f"savepwd_{u['id']}"):
                            if np1 and np1 == np2:
                                ok, msg = cambiar_password(u["id"], np1)
                                st.session_state[f"pwd_msg_{u['id']}"] = (ok, msg)
                                st.rerun()
                            else:
                                st.session_state[f"pwd_msg_{u['id']}"] = (False, "Las contraseñas no coinciden")
                                st.rerun()

                # Mensaje fuera del popover
                if f"pwd_msg_{u['id']}" in st.session_state:
                    ok_m, msg_m = st.session_state.pop(f"pwd_msg_{u['id']}")
                    if ok_m:
                        st.success(msg_m)
                    else:
                        st.warning(msg_m)

                # Activar / Desactivar
                with ua2:
                    if not es_yo:
                        lbl = "⛔ Desactivar" if u["activo"] else "✅ Activar"
                        if st.button(lbl, key=f"toggle_{u['id']}"):
                            toggle_usuario(u["id"], not u["activo"])
                            st.rerun()

                # Eliminar
                with ua3:
                    if not es_yo:
                        if st.button("🗑️ Eliminar", key=f"delusr_{u['id']}"):
                            if eliminar_usuario(u["id"]):
                                st.success("Usuario eliminado")
                                st.rerun()
                            else:
                                st.error("Error al eliminar")

        # ── Gestión de Motivos y Estatus de NC (solo Admin) ──────
        st.markdown("---")
        st.markdown("<div class='admin-hdr'>Motivos de Solicitud de NC</div>",
                    unsafe_allow_html=True)

        with st.expander("➕ Agregar nuevo motivo"):
            nuevo_mot = st.text_input("Texto del motivo", key="nuevo_motivo_txt")
            if st.button("Agregar motivo", key="btn_add_motivo"):
                if nuevo_mot.strip():
                    crear_nc_motivo(nuevo_mot.strip())
                    st.success("Motivo agregado")
                    st.rerun()

        for m in _cached_nc_motivos():
            mc1, mc2, mc3 = st.columns([5, 1, 1])
            with mc1:
                edit_mot = st.text_input("Motivo", value=m["texto"],
                                         key=f"edit_mot_{m['id']}",
                                         label_visibility="collapsed")
            with mc2:
                if st.button("💾", key=f"save_mot_{m['id']}"):
                    editar_nc_motivo(m["id"], edit_mot)
                    st.success("Actualizado")
                    st.rerun()
            with mc3:
                if st.button("🗑️", key=f"del_mot_{m['id']}"):
                    eliminar_nc_motivo(m["id"])
                    st.rerun()

        st.markdown("<div class='admin-hdr'>Estatus de NC</div>", unsafe_allow_html=True)

        with st.expander("➕ Agregar nuevo estatus"):
            nuevo_est = st.text_input("Texto del estatus", key="nuevo_estatus_txt")
            es_conc = st.checkbox("Marca la NC como concluida", key="nuevo_estatus_conc")
            if st.button("Agregar estatus", key="btn_add_estatus"):
                if nuevo_est.strip():
                    crear_nc_estatus(nuevo_est.strip(), es_conc)
                    st.success("Estatus agregado")
                    st.rerun()

        for e in _cached_nc_estatus():
            ec1, ec2, ec3 = st.columns([5, 1, 1])
            with ec1:
                edit_est = st.text_input("Estatus", value=e["texto"],
                                         key=f"edit_est_{e['id']}",
                                         label_visibility="collapsed")
            with ec2:
                if st.button("💾", key=f"save_est_{e['id']}"):
                    editar_nc_estatus(e["id"], edit_est, e.get("es_concluido", False))
                    st.success("Actualizado")
                    st.rerun()
            with ec3:
                if st.button("🗑️", key=f"del_est_{e['id']}"):
                    eliminar_nc_estatus(e["id"])
                    st.rerun()
