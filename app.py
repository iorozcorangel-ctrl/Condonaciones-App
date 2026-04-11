"""
================================================================
  SISTEMA DE CONDONACIONES — TERMINAL PORTUARIA PACÍFICO
  Versión Web — Streamlit
================================================================
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime
import io
import calendar

from app.config import FESTIVOS_FIJOS, FESTIVOS_VARIABLES, COL_BI, COL_TAB
from app.perfiles import (cargar_perfiles, guardar_perfiles, agregar_perfil,
                           modificar_perfil, eliminar_perfil,
                           cargar_ultimo_perfil_usado, guardar_ultimo_perfil_usado)
from app.calendario import (get_festivos_oficiales, calcular_desfase_regla3,
                             calcular_desfase_regla4, calcular_desfase_regla5)
from app.validaciones import (validar_archivos, aplicar_regla1, aplicar_regla2,
                               calcular_desfases, calcular_montos, generar_comentario)
from app.reporte import generar_reporte

# ── Configuración de página ─────────────────────────────────────
st.set_page_config(
    page_title="Sistema de Condonaciones",
    page_icon="🚢",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── CSS personalizado ───────────────────────────────────────────
st.markdown("""
<style>
.topbar {
    background: #1F4E79;
    padding: 16px 24px;
    border-radius: 8px;
    margin-bottom: 20px;
}
.topbar h1 {
    color: white;
    font-size: 22px;
    margin: 0;
    font-weight: 600;
}
.topbar p {
    color: #9ec5e8;
    font-size: 13px;
    margin: 4px 0 0 0;
}
.section-header {
    background: #1F4E79;
    color: white;
    padding: 8px 14px;
    border-radius: 6px;
    font-weight: 600;
    font-size: 14px;
    margin-bottom: 12px;
}
.cal-day-fest {
    background: #FFF3E0;
    color: #E65100;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 12px;
}
.cal-day-esp {
    background: #FFFDE7;
    color: #F57F17;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 12px;
}
.stButton > button {
    border-radius: 6px;
}
.alerta-box {
    background: #FFF3E0;
    border-left: 4px solid #E65100;
    padding: 10px 14px;
    border-radius: 4px;
    margin: 8px 0;
}
</style>
""", unsafe_allow_html=True)

# ── Inicializar estado de sesión ────────────────────────────────
def init_state():
    defaults = {
        "autenticado":       False,
        "df_tab":            None,
        "df_bi":             None,
        "perfiles":          cargar_perfiles(),
        "perfil_idx":        cargar_ultimo_perfil_usado(),
        "dias_especiales":   set(),
        "proceso_activo":    False,
        "desfases":          {},
        "montos":            {},
        "fechas_por_cont":   {},
        "desfases_confirmados": False,
        "alertas_acumuladas":[],
        "paso_actual":       "inicio",
        "df_tab_validado":   None,
        "df_bi_validado":    None,
        "fecha_revision":    date.today(),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ════════════════════════════════════════════════════════════════
#   PANTALLA DE LOGIN
# ════════════════════════════════════════════════════════════════

def pantalla_login():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style='text-align:center; padding: 40px 0 20px;'>
            <h2 style='color:#1F4E79;'>🚢 Sistema de Condonaciones</h2>
            <p style='color:#666;'>Terminal Portuaria Pacífico</p>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            pwd = st.text_input("Contraseña", type="password",
                                placeholder="Ingresa tu contraseña")
            submit = st.form_submit_button("Entrar", use_container_width=True)

        if submit:
            if pwd == st.secrets.get("password", ""):
                st.session_state["autenticado"] = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta")

# ════════════════════════════════════════════════════════════════
#   APLICACIÓN PRINCIPAL
# ════════════════════════════════════════════════════════════════

def app_principal():
    # Barra superior
    st.markdown("""
    <div class='topbar'>
        <h1>🚢 Sistema de Condonaciones</h1>
        <p>Terminal Portuaria Pacífico · Análisis de Gastos Extra</p>
    </div>
    """, unsafe_allow_html=True)

    # Layout principal: izquierda y derecha
    col_izq, col_der = st.columns([3, 2])

    with col_izq:
        seccion_perfil()
        seccion_datos_solicitud()
        seccion_archivos()
        seccion_botones()

    with col_der:
        seccion_calendario()

# ── Sección Perfil ──────────────────────────────────────────────

def seccion_perfil():
    st.markdown("<div class='section-header'>Perfil de Condonación</div>",
                unsafe_allow_html=True)

    perfiles  = st.session_state["perfiles"]
    nombres   = [p["nombre"] for p in perfiles]
    idx_actual = min(st.session_state["perfil_idx"], len(perfiles) - 1)

    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
    with col1:
        nuevo_idx = st.selectbox("Perfil activo", nombres,
                                  index=idx_actual,
                                  disabled=st.session_state["proceso_activo"],
                                  label_visibility="collapsed")
        idx_sel = nombres.index(nuevo_idx)
        if idx_sel != st.session_state["perfil_idx"]:
            st.session_state["perfil_idx"] = idx_sel
            guardar_ultimo_perfil_usado(idx_sel)

    with col2:
        if st.button("➕ Nuevo", use_container_width=True,
                     disabled=st.session_state["proceso_activo"]):
            st.session_state["mostrar_form_perfil"] = "nuevo"

    with col3:
        if st.button("✏️ Editar", use_container_width=True,
                     disabled=st.session_state["proceso_activo"] or idx_sel == 0):
            st.session_state["mostrar_form_perfil"] = "editar"

    with col4:
        if st.button("🗑️ Eliminar", use_container_width=True,
                     disabled=st.session_state["proceso_activo"] or idx_sel == 0):
            st.session_state["perfiles"] = eliminar_perfil(
                idx_sel, st.session_state["perfiles"]
            )
            st.session_state["perfil_idx"] = 0
            st.rerun()

    # Formulario de perfil
    if st.session_state.get("mostrar_form_perfil"):
        form_perfil()


def form_perfil():
    modo = st.session_state.get("mostrar_form_perfil", "nuevo")
    perfiles = st.session_state["perfiles"]
    p = perfiles[st.session_state["perfil_idx"]] if modo == "editar" else {}

    with st.expander("Configurar Perfil", expanded=True):
        nombre = st.text_input("Nombre del perfil",
                                value=p.get("nombre", ""))
        r1 = st.checkbox("¿Aplicar regla de 30 días naturales? (Regla 1)",
                          value=p.get("regla1_activa", True))
        r2 = st.checkbox("¿Aplicar regla de primeros 4 días? (Regla 2)",
                          value=p.get("regla2_activa", True))

        col1, col2, col3 = st.columns(3)
        with col1:
            dias_previo = st.number_input("Días para previo (Regla 3)",
                                           min_value=1, max_value=30,
                                           value=p.get("dias_previo", 3))
        with col2:
            dias_ffcc = st.number_input("Días para FFCC (Regla 4)",
                                         min_value=1, max_value=30,
                                         value=p.get("dias_ferromex", 3))
        with col3:
            dias_carr = st.number_input("Días para carretero (Regla 5)",
                                         min_value=1, max_value=30,
                                         value=p.get("dias_carretero", 2))

        col_g, col_c = st.columns(2)
        with col_g:
            if st.button("💾 Guardar perfil", use_container_width=True):
                if not nombre:
                    st.warning("El nombre es obligatorio")
                else:
                    nuevo_p = {
                        "nombre":         nombre,
                        "es_default":     False,
                        "regla1_activa":  r1,
                        "regla2_activa":  r2,
                        "dias_previo":    dias_previo,
                        "dias_ferromex":  dias_ffcc,
                        "dias_carretero": dias_carr,
                    }
                    if modo == "nuevo":
                        st.session_state["perfiles"] = agregar_perfil(
                            nuevo_p, st.session_state["perfiles"]
                        )
                        st.session_state["perfil_idx"] = len(st.session_state["perfiles"]) - 1
                    else:
                        st.session_state["perfiles"] = modificar_perfil(
                            st.session_state["perfil_idx"], nuevo_p,
                            st.session_state["perfiles"]
                        )
                    st.session_state["mostrar_form_perfil"] = None
                    st.rerun()
        with col_c:
            if st.button("Cancelar", use_container_width=True):
                st.session_state["mostrar_form_perfil"] = None
                st.rerun()

# ── Sección Datos de Solicitud ──────────────────────────────────

def seccion_datos_solicitud():
    st.markdown("<div class='section-header'>Datos de Solicitud</div>",
                unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        nc = st.text_input("N° de Nota de Crédito",
                            placeholder="Ej: NC-2585",
                            key="nc_cliente")
    with col2:
        fecha_str = st.text_input("Fecha de Solicitud NC (DD/MM/AAAA)",
                                   value=date.today().strftime("%d/%m/%Y"),
                                   key="fecha_solicitud_str")

    st.caption("La fecha aplica a todos los contenedores. "
               "Se puede modificar por contenedor en la previsualización.")

# ── Sección Archivos ────────────────────────────────────────────

def seccion_archivos():
    st.markdown("<div class='section-header'>Archivos de Entrada</div>",
                unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        archivo_tab = st.file_uploader(
            "📋 Subir Tabulador Comercial",
            type=["xlsx", "xls"],
            key="uploader_tab",
            disabled=st.session_state["proceso_activo"]
        )
        if archivo_tab:
            try:
                st.session_state["df_tab"] = pd.read_excel(archivo_tab)
                st.success(f"✔ {archivo_tab.name}")
            except Exception as e:
                st.error(f"Error al cargar: {e}")

    with col2:
        archivo_bi = st.file_uploader(
            "📊 Subir Archivo BI",
            type=["xlsx", "xls"],
            key="uploader_bi",
            disabled=st.session_state["proceso_activo"]
        )
        if archivo_bi:
            try:
                st.session_state["df_bi"] = pd.read_excel(archivo_bi)
                st.success(f"✔ {archivo_bi.name}")
            except Exception as e:
                st.error(f"Error al cargar: {e}")

# ── Sección Botones ─────────────────────────────────────────────

def seccion_botones():
    st.markdown("---")
    ambos = (st.session_state["df_tab"] is not None and
             st.session_state["df_bi"] is not None)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶ Iniciar Análisis",
                     disabled=not ambos or st.session_state["proceso_activo"],
                     use_container_width=True,
                     type="primary"):
            iniciar_analisis()

    with col2:
        if st.button("↺ Generar Nuevo Análisis",
                     use_container_width=True):
            nuevo_analisis()

# ── Sección Calendario ──────────────────────────────────────────

def seccion_calendario():
    st.markdown("<div class='section-header'>Días No Hábiles — Calendario</div>",
                unsafe_allow_html=True)

    hoy = date.today()

    if "cal_anio" not in st.session_state:
        st.session_state["cal_anio"] = hoy.year
    if "cal_mes" not in st.session_state:
        st.session_state["cal_mes"] = hoy.month

    col_ant, col_tit, col_sig = st.columns([1, 3, 1])
    meses_es = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
    with col_ant:
        if st.button("‹", key="cal_ant"):
            if st.session_state["cal_mes"] == 1:
                st.session_state["cal_mes"]  = 12
                st.session_state["cal_anio"] -= 1
            else:
                st.session_state["cal_mes"] -= 1
            st.rerun()
    with col_tit:
        st.markdown(f"**{meses_es[st.session_state['cal_mes']-1]} "
                    f"{st.session_state['cal_anio']}**")
    with col_sig:
        if st.button("›", key="cal_sig"):
            if st.session_state["cal_mes"] == 12:
                st.session_state["cal_mes"]  = 1
                st.session_state["cal_anio"] += 1
            else:
                st.session_state["cal_mes"] += 1
            st.rerun()

    # Dibujar calendario
    festivos = get_festivos_oficiales(st.session_state["cal_anio"])
    cal = calendar.Calendar(firstweekday=0)
    semanas = cal.monthdayscalendar(
        st.session_state["cal_anio"], st.session_state["cal_mes"]
    )

    dias_nombres = ["Lu","Ma","Mi","Ju","Vi","Sa","Do"]
    cols_header = st.columns(7)
    for i, d in enumerate(dias_nombres):
        color = "#E65100" if i >= 5 else "#666"
        cols_header[i].markdown(
            f"<div style='text-align:center;color:{color};font-size:12px;"
            f"font-weight:bold;'>{d}</div>", unsafe_allow_html=True
        )

    for semana in semanas:
        cols = st.columns(7)
        for i, dia in enumerate(semana):
            if dia == 0:
                cols[i].write("")
                continue

            fecha = date(st.session_state["cal_anio"],
                         st.session_state["cal_mes"], dia)
            es_finde   = i >= 5
            es_festivo = fecha in festivos
            es_esp     = fecha in st.session_state["dias_especiales"]
            es_hoy     = fecha == hoy

            if es_hoy:
                bg, fg = "#1F4E79", "white"
            elif es_esp:
                bg, fg = "#FFFDE7", "#F57F17"
            elif es_festivo:
                bg, fg = "#FFF3E0", "#E65100"
            elif es_finde:
                bg, fg = "#F0F0F0", "#999"
            else:
                bg, fg = "white", "#212121"

            label = f"**{dia}**" if es_hoy else str(dia)

            if cols[i].button(
                label, key=f"cal_{fecha}",
                disabled=st.session_state["proceso_activo"]
            ):
                if fecha in st.session_state["dias_especiales"]:
                    st.session_state["dias_especiales"].discard(fecha)
                else:
                    st.session_state["dias_especiales"].add(fecha)
                st.rerun()

    # Leyenda
    st.markdown("""
    <div style='font-size:11px;color:#666;margin-top:8px;'>
    🟧 Festivo oficial &nbsp;|&nbsp;
    🟨 Día especial &nbsp;|&nbsp;
    ⬜ Fin de semana &nbsp;|&nbsp;
    🟦 Hoy
    </div>
    """, unsafe_allow_html=True)

    # Días especiales marcados
    if st.session_state["dias_especiales"]:
        fechas_str = ", ".join(
            sorted(d.strftime("%d/%m/%Y")
                   for d in st.session_state["dias_especiales"])
        )
        st.caption(f"Días especiales: {fechas_str}")
    else:
        st.caption("Ningún día especial marcado · Clic en el calendario para marcar")

    if st.button("🗑️ Limpiar días especiales", key="limpiar_esp"):
        st.session_state["dias_especiales"] = set()
        st.rerun()

# ════════════════════════════════════════════════════════════════
#   LÓGICA DE ANÁLISIS
# ════════════════════════════════════════════════════════════════

def iniciar_analisis():
    perfil = st.session_state["perfiles"][st.session_state["perfil_idx"]]

    # Validar fecha
    fecha_str = st.session_state.get("fecha_solicitud_str", "")
    try:
        fecha_solicitud = datetime.strptime(fecha_str, "%d/%m/%Y").date()
    except ValueError:
        st.error("Formato de fecha inválido. Use DD/MM/AAAA")
        return

    nc_cliente = st.session_state.get("nc_cliente", "").strip()
    if not nc_cliente:
        st.warning("Por favor ingrese el número de nota de crédito")
        return

    # Validar archivos
    with st.spinner("Validando archivos..."):
        df_tab_v, df_bi_v, errores, advertencias = validar_archivos(
            st.session_state["df_tab"].copy(),
            st.session_state["df_bi"].copy()
        )

    if errores:
        for e in errores:
            st.error(e)
        st.session_state["df_tab"] = None
        st.session_state["df_bi"]  = None
        return

    if advertencias:
        for a in advertencias:
            st.warning(a)

    st.session_state["proceso_activo"]  = True
    st.session_state["df_tab_validado"] = df_tab_v
    st.session_state["df_bi_validado"]  = df_bi_v
    st.session_state["fecha_revision"]  = date.today()

    # Regla 1
    no_r1 = aplicar_regla1(df_bi_v, df_tab_v, fecha_solicitud,
                             st.session_state["fechas_por_cont"], perfil)
    if no_r1:
        conts = ", ".join(no_r1)
        st.warning(f"**Regla 1 — Plazo 30 días:** Los siguientes contenedores "
                   f"exceden el plazo: {conts}")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Sí, continuar de todas formas", key="r1_si"):
                pass
        with col2:
            if st.button("❌ No, cancelar", key="r1_no"):
                st.error("Condonación rechazada por no cumplir con los primeros 30 días")
                st.session_state["proceso_activo"] = False
                return

    # Regla 2
    no_r2 = aplicar_regla2(df_bi_v, perfil)
    if no_r2:
        conts = ", ".join(no_r2)
        st.warning(f"**Regla 2 — Primeros 4 días:** Los siguientes contenedores "
                   f"no cumplen: {conts}")

    # Calcular desfases
    with st.spinner("Calculando desfases..."):
        desfases = calcular_desfases(
            df_bi_v, st.session_state["dias_especiales"], perfil
        )

    # Alertas Liner y Reprogramaciones
    liners, reprog = [], []
    for _, row in df_bi_v.iterrows():
        cont = row[COL_BI["contenedor"]]
        fecha_auth = row.get(COL_BI["fecha_auth_naviera"])
        if pd.notna(fecha_auth) and str(fecha_auth).strip() not in ("", "nan"):
            liners.append(cont)
        try:
            if int(row.get(COL_BI["no_entregas"], 0)) >= 2:
                reprog.append(cont)
        except Exception:
            pass

    if liners:
        st.info(f"**Revisión Liner:** Revisar fecha de autorización de naviera "
                f"para: {', '.join(liners)}")
    if reprog:
        st.warning(f"**Reprogramaciones:** Los siguientes contenedores tienen "
                   f"más de 1 programación, favor validar fechas: {', '.join(reprog)}")

    # Calcular montos
    with st.spinner("Calculando montos..."):
        montos = calcular_montos(df_bi_v, desfases)

    st.session_state["desfases"] = desfases
    st.session_state["montos"]   = montos

    # Mostrar resumen de desfases
    st.markdown("### Resumen de días de desfase detectados")
    resumen_data = []
    for cont, d in desfases.items():
        resumen_data.append({
            "Contenedor":  cont,
            "Previo":      d["desfase_previo"],
            "FFCC":        d["desfase_ffcc"],
            "Carretero":   d["desfase_carretero"],
            "Total":       d["total_desfase"],
        })
    df_resumen = pd.DataFrame(resumen_data)
    st.dataframe(df_resumen, use_container_width=True, hide_index=True)

    # Confirmación y ajuste manual
    st.markdown("**¿Estás de acuerdo con los días de desfase calculados?**")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Sí, continuar", key="conf_si", type="primary"):
            generar_reporte_final(df_tab_v, df_bi_v, desfases, montos,
                                   fecha_solicitud, nc_cliente)
    with col2:
        if st.button("✏️ No, ajustar manualmente", key="conf_no"):
            st.session_state["mostrar_ajuste_manual"] = True
            st.rerun()

    if st.session_state.get("mostrar_ajuste_manual"):
        ajuste_manual(df_tab_v, df_bi_v, desfases, montos,
                       fecha_solicitud, nc_cliente)


def ajuste_manual(df_tab, df_bi, desfases, montos, fecha_solicitud, nc_cliente):
    st.markdown("### Ajuste Manual de Días de Desfase")

    dias_global = st.number_input("Días para TODOS los seleccionados",
                                   min_value=0, value=0, key="dias_global")

    contenedores = list(desfases.keys())
    seleccionados = {}
    dias_indiv = {}

    for cont in contenedores:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            sel = st.checkbox(cont, value=True, key=f"chk_{cont}")
            seleccionados[cont] = sel
        with col2:
            st.caption(f"Calculado: {desfases[cont]['total_desfase']} días")
        with col3:
            if not sel:
                dias_indiv[cont] = st.number_input(
                    "Días", min_value=0, value=0,
                    key=f"dias_{cont}", label_visibility="collapsed"
                )

    if st.button("💾 Guardar y continuar", type="primary"):
        for cont in contenedores:
            if seleccionados.get(cont, True):
                desfases[cont]["total_desfase"] = int(dias_global)
            else:
                desfases[cont]["total_desfase"] = int(dias_indiv.get(cont, 0))

        montos_nuevos = calcular_montos(df_bi, desfases)
        st.session_state["mostrar_ajuste_manual"] = False
        generar_reporte_final(df_tab, df_bi, desfases, montos_nuevos,
                               fecha_solicitud, nc_cliente)


def generar_reporte_final(df_tab, df_bi, desfases, montos,
                           fecha_solicitud, nc_cliente):
    fecha_revision = st.session_state["fecha_revision"]

    # Alerta almacenajes en 0
    sin_alm = []
    for _, row in df_bi.iterrows():
        try:
            if float(row.get(COL_BI["alm_qty"], 0) or 0) <= 0:
                sin_alm.append(row[COL_BI["contenedor"]])
        except Exception:
            pass

    if sin_alm:
        st.warning(f"No se detectaron almacenajes cobrados al cliente "
                   f"para: {', '.join(sin_alm)}")

    # Alerta Admon sin almacenajes
    admon_sin_alm = []
    for _, row in df_bi.iterrows():
        alm_qty   = float(row.get(COL_BI["alm_qty"], 0) or 0)
        admon_qty = float(row.get(COL_BI["admon_qty"], 0) or 0)
        if alm_qty <= 0 and admon_qty > 0:
            admon_sin_alm.append(row[COL_BI["contenedor"]])
    if admon_sin_alm:
        st.warning(f"Se detectó cobro de Servicio de Administración y Control "
                   f"sin almacenajes para: {', '.join(admon_sin_alm)}")

    with st.spinner("Generando reporte Excel..."):
        buffer = io.BytesIO()
        generar_reporte(
            df_tab, df_bi, desfases, montos,
            fecha_solicitud, fecha_revision, nc_cliente,
            st.session_state["fechas_por_cont"], buffer
        )
        buffer.seek(0)

    nombre_archivo = f"{nc_cliente or 'reporte_condonaciones'}.xlsx"
    st.success("¡Reporte generado exitosamente!")
    st.download_button(
        label="⬇️ Descargar Reporte Excel",
        data=buffer,
        file_name=nombre_archivo,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
    st.session_state["proceso_activo"] = False


def nuevo_analisis():
    keys_a_limpiar = ["df_tab", "df_bi", "df_tab_validado", "df_bi_validado",
                       "desfases", "montos", "fechas_por_cont",
                       "proceso_activo", "mostrar_ajuste_manual"]
    for k in keys_a_limpiar:
        if k in st.session_state:
            st.session_state[k] = None if "df" in k else (
                {} if isinstance(st.session_state.get(k), dict) else False
            )
    st.session_state["proceso_activo"] = False
    st.rerun()

# ════════════════════════════════════════════════════════════════
#   PUNTO DE ENTRADA
# ════════════════════════════════════════════════════════════════

if not st.session_state["autenticado"]:
    pantalla_login()
else:
    app_principal()
