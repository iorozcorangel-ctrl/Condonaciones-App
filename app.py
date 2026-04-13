"""
================================================================
  SISTEMA DE CONDONACIONES — TERMINAL PORTUARIA 
  Versión Web — Streamlit + Supabase
================================================================
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime
from zoneinfo import ZoneInfo
import io
import calendar

ZONA_MX = ZoneInfo("America/Mexico_City")

def hoy_mx():
    """Retorna la fecha actual en zona horaria de México."""
    return datetime.now(ZONA_MX).date()

from app.config import COL_BI, COL_TAB
from app.perfiles import (cargar_perfiles, agregar_perfil, modificar_perfil,
                           eliminar_perfil, cargar_ultimo_perfil_usado,
                           guardar_ultimo_perfil_usado)
from app.calendario import get_festivos_oficiales
from app.validaciones import (validar_archivos, aplicar_regla1, aplicar_regla2,
                               calcular_desfases, calcular_montos)
from app.reporte import generar_reporte
from app.database import (login_usuario, obtener_usuarios, crear_usuario,
                           cambiar_password, toggle_usuario, eliminar_usuario,
                           registrar_nc, verificar_duplicados,
                           obtener_historial, obtener_detalle_nc, eliminar_nc)

st.set_page_config(
    page_title="Sistema de Condonaciones",
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
        "perfiles":          cargar_perfiles(),
        "perfil_idx":        cargar_ultimo_perfil_usado(),
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
    }
    for k, v in defs.items():
        if k not in st.session_state:
            st.session_state[k] = v

init()

# ════════════════════════════════════════════════════════════════
#   PANTALLA DE LOGIN
# ════════════════════════════════════════════════════════════════
if st.session_state["usuario"] is None:
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("""
        <div style='text-align:center;padding:40px 0 20px;'>
          <h2 style='color:#E65100;'>🚢 Sistema de Condonaciones</h2>
          <p style='color:#666;'>Terminal Portuaria</p>
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
                        st.session_state["usuario"] = usuario
                        st.rerun()
                    else:
                        st.error("Usuario o contraseña incorrectos")
    st.stop()

# ════════════════════════════════════════════════════════════════
#   APP PRINCIPAL — Usuario autenticado
# ════════════════════════════════════════════════════════════════

usuario     = st.session_state["usuario"]
es_admin    = usuario["rol"] == "admin"
nombre_user = usuario["nombre_completo"]
rol_badge   = "badge-admin" if es_admin else "badge-user"
rol_label   = "Administrador" if es_admin else "Usuario"

# ── Barra superior ──────────────────────────────────────────────
col_titulo, col_user = st.columns([4, 1])
with col_titulo:
    st.markdown("""
    <div class='topbar'>
      <h1>🚢 Sistema de Condonaciones</h1>
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
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ── Navegación ──────────────────────────────────────────────────
tabs_disponibles = ["📊 Análisis", "📋 Historial NC", "📖 Reglas de Aplicación"]
if es_admin:
    tabs_disponibles.append("👥 Usuarios")

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
                guardar_ultimo_perfil_usado(nuevo_idx)
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
                st.session_state["perfiles"] = eliminar_perfil(nuevo_idx, perfiles)
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
                dp = pc1.number_input("Días previo (R3)", 1, 30, p.get("dias_previo", 3))
                df = pc2.number_input("Días FFCC (R4)",   1, 30, p.get("dias_ferromex", 3))
                dc = pc3.number_input("Días carretero (R5)", 1, 30, p.get("dias_carretero", 2))
                bg1, bg2 = st.columns(2)
                if bg1.button("💾 Guardar", use_container_width=True):
                    if nombre_p:
                        np2 = {"nombre": nombre_p, "es_default": False,
                               "regla1_activa": r1, "regla2_activa": r2,
                               "dias_previo": dp, "dias_ferromex": df,
                               "dias_carretero": dc}
                        if modo == "nuevo":
                            st.session_state["perfiles"] = agregar_perfil(
                                np2, st.session_state["perfiles"])
                            st.session_state["perfil_idx"] = len(st.session_state["perfiles"]) - 1
                        else:
                            st.session_state["perfiles"] = modificar_perfil(
                                nuevo_idx, np2, st.session_state["perfiles"])
                        st.session_state["mostrar_form_perfil"] = None
                        st.rerun()
                if bg2.button("Cancelar", use_container_width=True):
                    st.session_state["mostrar_form_perfil"] = None
                    st.rerun()

        # ── Resumen informativo del perfil ────────────────────
        perfil_activo = st.session_state["perfiles"][nuevo_idx]
        r1_txt = "✅ Activa" if perfil_activo.get("regla1_activa", True) else "❌ Desactivada"
        r2_txt = "✅ Activa" if perfil_activo.get("regla2_activa", True) else "❌ Desactivada"
        dp_txt = perfil_activo.get("dias_previo",    3)
        df_txt = perfil_activo.get("dias_ferromex",  3)
        dc_txt = perfil_activo.get("dias_carretero", 2)
        st.markdown(f"""
        <div style='background:#FFF3E0;border-left:4px solid #E65100;padding:10px 14px;
                    border-radius:4px;font-size:13px;color:#555;margin-bottom:8px;'>
        <b>Configuración del perfil activo:</b><br>
        📅 <b>Regla 1</b> — Validación 30 días naturales: {r1_txt}<br>
        📅 <b>Regla 2</b> — Validación primeros 4 días: {r2_txt}<br>
        🔄 <b>Regla 3</b> — Plazo para posicionamiento de previo: <b>{dp_txt} días hábiles</b> (Lun–Sáb)<br>
        🚂 <b>Regla 4</b> — Plazo para carga a góndola FFCC: <b>{df_txt} días naturales</b><br>
        🚚 <b>Regla 5</b> — Plazo para entrega carretero: <b>{dc_txt} días hábiles</b> (excepto Sáb si programó Jue/Vie)
        </div>
        """, unsafe_allow_html=True)

        # ── Datos de solicitud ────────────────────────────────
        st.markdown("<div class='sec-hdr'>Datos de Solicitud</div>",
                    unsafe_allow_html=True)
        dc1, dc2 = st.columns(2)
        # Reset NC y fecha — usar input_key para forzar re-render
        ikey = st.session_state["uploader_key"]
        nc_input = dc1.text_input("N° Nota de Crédito",
                                   placeholder="Ej: NC-2585",
                                   disabled=bloqueado,
                                   key=f"nc_input_{ikey}")

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
                    alertas.append(("duplicado",
                        f"⚠️ La factura **{dup['factura']}** ya fue registrada "
                        f"en la NC **{dup['nc_anterior']}** "
                        f"(fecha: {dup['fecha']}). Verifique antes de continuar."))

            with st.spinner("Calculando desfases..."):
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
                        cont = row[COL_BI["contenedor"]]
                        desfases[cont] = {
                            "desfase_previo":    dp_m,
                            "desfase_ffcc":      df_m,
                            "desfase_carretero": dc_m,
                            "total_desfase":     dp_m + df_m + dc_m,
                            "es_manual":         True,
                        }
                else:
                    desfases = calcular_desfases(
                        df_bv, st.session_state["dias_especiales"], perfil
                    )
                    for cont in desfases:
                        desfases[cont]["es_manual"] = False

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
            st.session_state["paso"]            = "confirmacion"
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

if es_admin:
    with nav[3]:
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
            usuarios = obtener_usuarios()

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
