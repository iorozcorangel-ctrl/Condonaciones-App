"""
================================================================
  SISTEMA DE CONDONACIONES — TERMINAL PORTUARIA PACÍFICO
  Versión Web — Streamlit + Supabase
================================================================
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime
import io
import calendar

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
        "fecha_revision":    date.today(),
        "cal_anio":          date.today().year,
        "cal_mes":           date.today().month,
        "mostrar_form_perfil": None,
        "alertas":           [],
        "uploader_key":      0,
        "vista":             "analisis",  # analisis | historial | usuarios
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
tabs_disponibles = ["📊 Análisis", "📋 Historial NC"]
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

        # ── Datos de solicitud ────────────────────────────────
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
            st.session_state["fecha_revision"]  = date.today()
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
                st.session_state["df_tab"]        = None
                st.session_state["df_bi"]         = None
                st.session_state["df_tab_v"]      = None
                st.session_state["df_bi_v"]       = None
                st.session_state["desfases"]      = {}
                st.session_state["montos"]        = {}
                st.session_state["alertas"]       = []
                st.session_state["paso"]          = "inicio"
                st.session_state["uploader_key"] += 1
                st.session_state["nc_registrada"] = False
                st.rerun()

    # ── Panel derecho: Calendario ─────────────────────────────
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
        historial = obtener_historial()

    if not historial:
        st.info("No hay notas de crédito registradas aún.")
    else:
        for reg in historial:
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

# ════════════════════════════════════════════════════════════════
#   PESTAÑA 3 — USUARIOS (solo admin)
# ════════════════════════════════════════════════════════════════
if es_admin:
    with nav[2]:
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
