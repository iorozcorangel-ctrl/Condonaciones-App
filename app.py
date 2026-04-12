"""
================================================================
  SISTEMA DE CONDONACIONES — TERMINAL PORTUARIA
  Versión Web — Streamlit
================================================================
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime
import io
import calendar

from app.config import COL_BI, COL_TAB
from app.perfiles import (cargar_perfiles, agregar_perfil,
                           modificar_perfil, eliminar_perfil,
                           cargar_ultimo_perfil_usado, guardar_ultimo_perfil_usado)
from app.calendario import get_festivos_oficiales
from app.validaciones import (validar_archivos, aplicar_regla1, aplicar_regla2,
                               calcular_desfases, calcular_montos)
from app.reporte import generar_reporte

st.set_page_config(
    page_title="Sistema de Condonaciones",
    page_icon="🚢",
    layout="wide"
)

st.markdown("""
<style>
.topbar{background:#1F4E79;padding:16px 24px;border-radius:8px;margin-bottom:20px;}
.topbar h1{color:white;font-size:22px;margin:0;font-weight:600;}
.topbar p{color:#9ec5e8;font-size:13px;margin:4px 0 0 0;}
.sec-hdr{background:#1F4E79;color:white;padding:8px 14px;border-radius:6px;
         font-weight:600;font-size:14px;margin-bottom:12px;}
</style>
""", unsafe_allow_html=True)

# ── Estado inicial ──────────────────────────────────────────────
def init():
    defs = {
        "autenticado":         False,
        "df_tab":              None,
        "df_bi":               None,
        "df_tab_v":            None,
        "df_bi_v":             None,
        "perfiles":            cargar_perfiles(),
        "perfil_idx":          cargar_ultimo_perfil_usado(),
        "dias_especiales":     set(),
        "paso":                "inicio",
        "desfases":            {},
        "montos":              {},
        "fecha_solicitud":     None,
        "nc_cliente":          "",
        "fecha_revision":      date.today(),
        "cal_anio":            date.today().year,
        "cal_mes":             date.today().month,
        "mostrar_form_perfil": None,
        "alertas":             [],       # alertas acumuladas para mostrar
        "uploader_key":        0,        # key dinámica para resetear uploaders
    }
    for k, v in defs.items():
        if k not in st.session_state:
            st.session_state[k] = v

init()

# ════════════════════════════════════════════════════════════════
#   LOGIN
# ════════════════════════════════════════════════════════════════
if not st.session_state["autenticado"]:
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.markdown("<h2 style='text-align:center;color:#1F4E79;'>🚢 Sistema de Condonaciones</h2>",
                    unsafe_allow_html=True)
        st.markdown("<p style='text-align:center;color:#666;'>Terminal Portuaria Pacífico</p>",
                    unsafe_allow_html=True)
        with st.form("login"):
            pwd = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Entrar", use_container_width=True):
                if pwd == st.secrets.get("password", ""):
                    st.session_state["autenticado"] = True
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta")
    st.stop()

# ════════════════════════════════════════════════════════════════
#   APP PRINCIPAL
# ════════════════════════════════════════════════════════════════

st.markdown("""
<div class='topbar'>
  <h1>🚢 Sistema de Condonaciones</h1>
  <p>Terminal Portuaria Pacífico · Análisis de Gastos Extra</p>
</div>
""", unsafe_allow_html=True)

col_izq, col_der = st.columns([3, 2])

# ════════════════════════════════════════════════════════════════
#   PANEL IZQUIERDO
# ════════════════════════════════════════════════════════════════
with col_izq:

    # ── Perfil ────────────────────────────────────────────────
    st.markdown("<div class='sec-hdr'>Perfil de Condonación</div>",
                unsafe_allow_html=True)
    perfiles = st.session_state["perfiles"]
    nombres  = [p["nombre"] for p in perfiles]
    idx      = min(st.session_state["perfil_idx"], len(perfiles)-1)
    bloqueado = st.session_state["paso"] != "inicio"

    c1, c2, c3, c4 = st.columns([3,1,1,1])
    with c1:
        sel = st.selectbox("Perfil", nombres, index=idx,
                           label_visibility="collapsed",
                           disabled=bloqueado)
        nuevo_idx = nombres.index(sel)
        if nuevo_idx != st.session_state["perfil_idx"]:
            st.session_state["perfil_idx"] = nuevo_idx
            guardar_ultimo_perfil_usado(nuevo_idx)
    with c2:
        if st.button("➕ Nuevo", use_container_width=True, disabled=bloqueado):
            st.session_state["mostrar_form_perfil"] = "nuevo"
    with c3:
        if st.button("✏️ Editar", use_container_width=True,
                     disabled=nuevo_idx == 0 or bloqueado):
            st.session_state["mostrar_form_perfil"] = "editar"
    with c4:
        if st.button("🗑️", use_container_width=True,
                     disabled=nuevo_idx == 0 or bloqueado):
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
            dp = pc1.number_input("Días previo (R3)",    1, 30, p.get("dias_previo",    3))
            df = pc2.number_input("Días FFCC (R4)",      1, 30, p.get("dias_ferromex",  3))
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

    # ── Datos de solicitud ────────────────────────────────────
    st.markdown("<div class='sec-hdr'>Datos de Solicitud</div>",
                unsafe_allow_html=True)
    dc1, dc2 = st.columns(2)
    nc_input    = dc1.text_input("N° Nota de Crédito",
                                  placeholder="Ej: NC-2585",
                                  disabled=bloqueado)
    fecha_input = dc2.text_input("Fecha Solicitud NC (DD/MM/AAAA)",
                                  value=date.today().strftime("%d/%m/%Y"),
                                  disabled=bloqueado)
    st.caption("La fecha aplica a todos los contenedores.")

    # ── Archivos ──────────────────────────────────────────────
    st.markdown("<div class='sec-hdr'>Archivos de Entrada</div>",
                unsafe_allow_html=True)

    # Key dinámica para poder resetear los uploaders
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

    # ── Botones principales ───────────────────────────────────
    st.markdown("---")
    ambos = (st.session_state["df_tab"] is not None and
             st.session_state["df_bi"] is not None)

    bb1, bb2 = st.columns(2)
    with bb1:
        iniciar = st.button("▶ Iniciar Análisis",
                            disabled=not ambos or bloqueado,
                            use_container_width=True,
                            type="primary")
    with bb2:
        if st.button("↺ Nuevo Análisis", use_container_width=True):
            # Resetear todo incluyendo uploaders con nueva key
            st.session_state["df_tab"]       = None
            st.session_state["df_bi"]        = None
            st.session_state["df_tab_v"]     = None
            st.session_state["df_bi_v"]      = None
            st.session_state["desfases"]     = {}
            st.session_state["montos"]       = {}
            st.session_state["alertas"]      = []
            st.session_state["paso"]         = "inicio"
            st.session_state["uploader_key"] += 1  # fuerza reset de uploaders
            st.rerun()

    # ── Mostrar alertas acumuladas ────────────────────────────
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

    # ════════════════════════════════════════════════════════
    #   FLUJO: INICIAR ANÁLISIS
    # ════════════════════════════════════════════════════════
    if iniciar:
        try:
            fecha_sol = datetime.strptime(fecha_input, "%d/%m/%Y").date()
        except ValueError:
            st.error("Formato de fecha inválido. Use DD/MM/AAAA")
            st.stop()

        if not nc_input.strip():
            st.warning("Ingrese el número de nota de crédito")
            st.stop()

        perfil = st.session_state["perfiles"][st.session_state["perfil_idx"]]
        alertas = []

        with st.spinner("Validando archivos..."):
            df_tv, df_bv, errores, advertencias = validar_archivos(
                st.session_state["df_tab"].copy(),
                st.session_state["df_bi"].copy()
            )

        if errores:
            for e in errores:
                st.error(e)
            st.session_state["df_tab"] = None
            st.session_state["df_bi"]  = None
            st.session_state["uploader_key"] += 1
            st.rerun()

        for a in advertencias:
            alertas.append(("warning", a))

        with st.spinner("Calculando desfases..."):
            desfases = calcular_desfases(
                df_bv, st.session_state["dias_especiales"], perfil
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

        # Alertas liner y reprogramaciones
        liners, reprog = [], []
        for _, row in df_bv.iterrows():
            cont = row[COL_BI["contenedor"]]
            fa2  = row.get(COL_BI["fecha_auth_naviera"])
            if pd.notna(fa2) and str(fa2).strip() not in ("", "nan"):
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

        # Guardar todo en sesión y avanzar
        st.session_state["df_tab_v"]        = df_tv
        st.session_state["df_bi_v"]         = df_bv
        st.session_state["desfases"]        = desfases
        st.session_state["montos"]          = montos
        st.session_state["fecha_solicitud"] = fecha_sol
        st.session_state["nc_cliente"]      = nc_input.strip()
        st.session_state["fecha_revision"]  = date.today()
        st.session_state["alertas"]         = alertas
        st.session_state["paso"]            = "confirmacion"
        st.rerun()

    # ════════════════════════════════════════════════════════
    #   FLUJO: CONFIRMACIÓN DE DESFASES
    # ════════════════════════════════════════════════════════
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

    # ════════════════════════════════════════════════════════
    #   FLUJO: AJUSTE MANUAL
    # ════════════════════════════════════════════════════════
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

    # ════════════════════════════════════════════════════════
    #   FLUJO: GENERAR REPORTE
    # ════════════════════════════════════════════════════════
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
                     if float(row.get(COL_BI["alm_qty"],  0) or 0) <= 0
                     and float(row.get(COL_BI["admon_qty"], 0) or 0) > 0]
        if admon_sin:
            st.warning(f"Cobro Admin y Control sin almacenajes: "
                       f"{', '.join(admon_sin)}")

        with st.spinner("Generando reporte Excel..."):
            buffer = io.BytesIO()
            generar_reporte(df_tv, df_bv, desfases, montos,
                            fecha_sol, fecha_rev, nc, {}, buffer)
            buffer.seek(0)

        st.success("¡Reporte generado exitosamente!")
        st.download_button(
            label="⬇️ Descargar Reporte Excel",
            data=buffer,
            file_name=f"{nc or 'reporte'}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

        st.markdown("---")
        if st.button("↺ Realizar nuevo análisis", use_container_width=True):
            st.session_state["df_tab"]       = None
            st.session_state["df_bi"]        = None
            st.session_state["df_tab_v"]     = None
            st.session_state["df_bi_v"]      = None
            st.session_state["desfases"]     = {}
            st.session_state["montos"]       = {}
            st.session_state["alertas"]      = []
            st.session_state["paso"]         = "inicio"
            st.session_state["uploader_key"] += 1
            st.rerun()

# ════════════════════════════════════════════════════════════════
#   PANEL DERECHO — CALENDARIO
# ════════════════════════════════════════════════════════════════
with col_der:
    st.markdown("<div class='sec-hdr'>Días No Hábiles — Calendario</div>",
                unsafe_allow_html=True)

    hoy      = date.today()
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

    dias_n = ["Lu","Ma","Mi","Ju","Vi","Sa","Do"]
    hcols  = st.columns(7)
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

            if es_hoy:
                bg = "🟦"
            elif es_esp:
                bg = "🟨"
            elif es_fest:
                bg = "🟧"
            elif es_finde:
                bg = "⬜"
            else:
                bg = "  "

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
