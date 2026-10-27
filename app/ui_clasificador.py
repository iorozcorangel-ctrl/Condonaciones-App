"""
================================================================
  PANTALLAS DEL MÓDULO "🔧 Clasificador de Casos"
  Sub-pestañas: 🔍 Clasificar · 📚 Catálogo · 💡 Sugerencias
  Se llama desde app.py:  render_clasificador(usuario, es_admin)
================================================================
"""
import html

import pandas as pd
import streamlit as st

from app import clasificador as cl
from app import database as dbm

TIPOS_SUG = {
    "nuevo":    "➕ Motivo nuevo",
    "corregir": "✏️ Corregir un motivo existente",
    "palabras": "🔑 Palabras clave / diferenciador",
    "baja":     "🚫 Dar de baja un motivo",
}
NIVEL_TXT = {
    "alta":  ("success", "Confianza alta: la primera opción sobresale claramente."),
    "media": ("warning", "Confianza media: revisa la primera opción antes de usarla."),
    "baja":  ("error",   "Confianza baja: el correo es vago o no se parece a ningún motivo. "
                         "Revisa las opciones o búscalo en el catálogo."),
}


# ── Datos con caché (se limpia al modificar) ──────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def _motivos_todos():
    return dbm.obtener_clasif_motivos(incluir_inactivos=True)


@st.cache_data(ttl=10, show_spinner=False)
def _sug_pendientes():
    return dbm.obtener_clasif_sugerencias(estado="pendiente")


def invalidar_cache_clasificador():
    _motivos_todos.clear()
    _sug_pendientes.clear()


def _activos():
    return [m for m in _motivos_todos() if m.get("activo", True)]


@st.cache_resource(show_spinner=False)
def _indice_para(firma: tuple):
    # firma = (id, fecha_actualizacion) de cada motivo activo → se reconstruye solo si algo cambió
    return cl.construir_indice(_activos())


def _indice():
    act = _activos()
    return _indice_para(tuple((m.get("id"), m.get("fecha_actualizacion")) for m in act))


def _esc(t):
    return html.escape(str(t or ""))


# ── Avisos al iniciar sesión (los llama app.py una vez por sesión) ──
def avisos_inicio_sesion(usuario: dict, es_admin: bool):
    try:
        if es_admin:
            n = len(dbm.obtener_clasif_sugerencias(estado="pendiente"))
            if n:
                st.toast(f"🔧 Hay {n} sugerencia(s) del Clasificador de Casos por revisar.", icon="🔔")
        else:
            res = dbm.obtener_clasif_sugerencias_sin_notificar(usuario["id"])
            for r in res:
                nombre = r.get("motivo_nombre") or (r.get("propuesta") or {}).get("motivo") or ""
                if r["estado"] == "aprobada":
                    st.toast(f"✅ Tu sugerencia del Clasificador ({nombre}) fue APROBADA.", icon="✅")
                else:
                    st.toast(f"❌ Tu sugerencia del Clasificador ({nombre}) fue RECHAZADA. "
                             f"Motivo: {r.get('motivo_rechazo') or 'sin motivo'}", icon="❌")
            dbm.marcar_clasif_sugerencias_notificadas([r["id"] for r in res])
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
def render_clasificador(usuario: dict, es_admin: bool):
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""<div class='clf-cab'>
              <img class='clf-masc' alt='Mascota' width='190' style='width:190px;max-width:40vw;height:auto;image-rendering:pixelated' src='data:image/png;base64,{cl.MASCOTA_PNG_B64}'>
              <div class='clf-globo'><b>¡Ajusto cada caso a su área!</b><br>
              Pega el correo del cliente o busca en el catálogo de tipos de caso.</div>
              {_ESCENA_HTML}
            </div>""", unsafe_allow_html=True)

    if not _motivos_todos():
        st.warning("El catálogo está vacío o aún no existe en la base de datos. "
                   "Corre el archivo **SQL_clasificador_casos.sql** en Supabase "
                   "(o, si eres admin, importa el Excel en 📚 Catálogo).")

    n_pend = len(_sug_pendientes()) if es_admin else 0
    tabs = st.tabs(["🔍 Clasificar", "📚 Catálogo",
                    f"💡 Sugerencias{f' ({n_pend})' if n_pend else ''}"])
    with tabs[0]:
        _tab_clasificar(usuario)
    with tabs[1]:
        _tab_catalogo(usuario, es_admin)
    with tabs[2]:
        _tab_sugerencias(usuario, es_admin)


# ── 🔍 Clasificar ──────────────────────────────────────────────
def _tab_clasificar(usuario):
    c1, c2 = st.columns([1.15, 1])
    with c1:
        st.markdown("<div class='sec-hdr'>✉️ Clasificar un correo</div>", unsafe_allow_html=True)
        with st.form("clf_form_correo"):
            texto = st.text_area("Pega el correo del cliente (asunto y cuerpo)", height=200,
                                 key="clf_texto",
                                 placeholder="Ej.: Hola, no puedo entrar al portal ISCS, me sale que mi "
                                             "sesión está bloqueada por adeudo…")
            ok = st.form_submit_button("🔍 Sugerir motivo", type="primary")
        if ok:
            st.session_state["clf_resultado"] = cl.clasificar(texto, _indice(), top=3) if texto.strip() else None
            st.session_state["clf_texto_usado"] = texto
            st.session_state["clf_confirmado"] = None
        st.caption("🔒 El correo no se guarda. Si confirmas un motivo, solo se envían al admin "
                   "palabras clave útiles (sin nombres, RFC, contenedores ni números).")
    with c2:
        st.markdown("<div class='sec-hdr'>🔎 Buscar en el catálogo</div>", unsafe_allow_html=True)
        q = st.text_input("Escribe palabras (ej. cita, sello, factura, credencial)", key="clf_buscar")
        if q.strip():
            encontrados = cl.buscar(q, _activos(), _indice(), limite=12)
            if not encontrados:
                st.info("Sin coincidencias. Prueba con otra palabra.")
            for m in encontrados:
                with st.expander(f"{m['motivo']}  ·  {m.get('area') or '—'}"):
                    _detalle_motivo(m)

    R = st.session_state.get("clf_resultado")
    if R is None:
        return
    st.markdown("<div class='sec-hdr'>💡 Sugerencias</div>", unsafe_allow_html=True)
    if not R["items"]:
        st.error("Ninguna palabra del correo coincide con el catálogo. Búscalo a mano a la derecha, "
                 "o manda una sugerencia en 💡 Sugerencias si falta el motivo.")
        return
    tipo, msg = NIVEL_TXT[R["nivel"]]
    if R["empate"]:
        msg += " Hay empate entre las primeras opciones: decide por el área."
    getattr(st, tipo)(msg)

    for i, it in enumerate(R["items"]):
        m = it["motivo"]
        with st.container(border=True):
            h1, h2 = st.columns([4, 1])
            h1.markdown(f"**{i + 1}. {_esc(m['motivo'])}**")
            h2.markdown(f"<span class='clf-area'>{_esc(m.get('area'))}</span>", unsafe_allow_html=True)
            if m.get("descripcion"):
                st.caption(m["descripcion"])
            if (m.get("no_confundir") or "").strip():
                st.markdown(f"<div class='clf-nc'>⚠️ No confundir con: {_esc(m['no_confundir'])}</div>",
                            unsafe_allow_html=True)
            st.progress(it["rel"] / 100, text=f"Coincidencia relativa: {it['rel']}%")
            st.markdown(" ".join(f"<span class='clf-chip'>{_esc(h)}</span>" for h in it["hits"][:12]),
                        unsafe_allow_html=True)
            if st.button("✅ Es este motivo", key=f"clf_conf_{i}_{m.get('id')}",
                         type="primary" if i == 0 else "secondary"):
                _confirmar(usuario, m)
    conf = st.session_state.get("clf_confirmado")
    if conf:
        st.success(f"Caso clasificado como **{conf['motivo']}** → área **{conf.get('area')}**. "
                   + (conf.get("_msg") or ""))


def _confirmar(usuario, m):
    """Confirmar NO cambia el catálogo: manda las palabras útiles al admin como sugerencia."""
    texto = st.session_state.get("clf_texto_usado", "")
    palabras = cl.extraer_palabras_clave(texto)
    ya = {cl.normalizar(p) for p in (m.get("palabras_clave") or "").split(",")}
    nuevas = [p for p in palabras if p not in ya]
    msg = ""
    if nuevas:
        ok, _ = dbm.crear_clasif_sugerencia(
            "palabras", {"palabras_clave": ", ".join(nuevas)},
            "Generada al confirmar la clasificación de un correo.",
            usuario["id"], usuario["nombre_completo"], m.get("id"), m.get("motivo"))
        if ok:
            _sug_pendientes.clear()
            msg = ("Se enviaron al admin estas palabras para que el clasificador aprenda: "
                   + ", ".join(nuevas) + ".")
    st.session_state["clf_confirmado"] = dict(m, _msg=msg)


def _detalle_motivo(m):
    st.markdown(f"**Área:** {_esc(m.get('area'))}")
    if m.get("descripcion"):
        st.markdown(f"**Cuándo aplica:** {_esc(m['descripcion'])}")
    if (m.get("palabras_clave") or "").strip():
        st.markdown(f"**Palabras clave:** {_esc(m['palabras_clave'])}")
    if (m.get("no_confundir") or "").strip():
        st.markdown(f"**No confundir con:** {_esc(m['no_confundir'])}")


# ── 📚 Catálogo ─────────────────────────────────────────────────
def _tab_catalogo(usuario, es_admin):
    todos = _motivos_todos()
    activos = [m for m in todos if m.get("activo", True)]
    areas = sorted({m.get("area") or "—" for m in activos})
    f1, f2, f3 = st.columns([1, 2, 1])
    area_sel = f1.selectbox("Área", ["Todas"] + areas, key="clf_cat_area")
    txt = f2.text_input("Filtrar por texto", key="clf_cat_txt")
    ver_inact = f3.checkbox("Ver dados de baja", key="clf_cat_inact") if es_admin else False
    lista = todos if ver_inact else activos
    if area_sel != "Todas":
        lista = [m for m in lista if (m.get("area") or "—") == area_sel]
    if txt.strip():
        t = cl.normalizar(txt)
        lista = [m for m in lista if t in cl.normalizar(" ".join(
            str(m.get(k) or "") for k in ("motivo", "area", "descripcion", "palabras_clave", "no_confundir")))]
    st.caption(f"{len(lista)} motivo(s) · {len(activos)} activos en total · {len(areas)} áreas")
    if lista:
        st.dataframe(pd.DataFrame([{
            "Motivo": m["motivo"], "Área": m.get("area"), "Cuándo aplica": m.get("descripcion"),
            "Palabras clave": m.get("palabras_clave") or "", "No confundir con": m.get("no_confundir") or "",
            **({"Activo": "Sí" if m.get("activo", True) else "No"} if es_admin else {}),
        } for m in lista]), hide_index=True, width='stretch', height=min(420, 40 + 35 * len(lista)))

    st.download_button("📤 Descargar catálogo en Excel", data=cl.exportar_excel(todos if es_admin else activos),
                       file_name="catalogo_tipos_de_caso.xlsx", key="clf_exportar",
                       help="Mismo formato que se importa: puedes editarlo y volver a subirlo.")

    if not es_admin:
        st.info("¿Falta algo o algo está mal? Mándalo en la pestaña 💡 Sugerencias; el admin lo revisa.")
        return

    # ── Admin: editar / agregar ──
    st.markdown("<div class='admin-hdr'>✏️ Editar o agregar un motivo (admin)</div>", unsafe_allow_html=True)
    opciones = ["➕ Nuevo motivo"] + [f"{m['motivo']}  ·  {m.get('area')}" + ("" if m.get("activo", True) else "  (baja)")
                                     for m in sorted(todos, key=lambda x: cl.normalizar(x["motivo"]))]
    orden = sorted(todos, key=lambda x: cl.normalizar(x["motivo"]))
    sel = st.selectbox("Motivo", opciones, key="clf_edit_sel")
    m = None if sel == opciones[0] else orden[opciones.index(sel) - 1]
    kid = (m or {}).get("id", "nuevo")
    with st.form(f"clf_form_edit_{kid}"):
        e_mot = st.text_input("Motivo de caso *", value=(m or {}).get("motivo", ""))
        e_area = st.selectbox("Área *", areas + ["(otra área…)"],
                              index=areas.index(m["area"]) if m and m.get("area") in areas else 0)
        e_area_otra = st.text_input("Si elegiste «otra área», escríbela aquí")
        e_desc = st.text_area("Cuándo aplica", value=(m or {}).get("descripcion", ""), height=110)
        e_pal = st.text_area("Palabras clave (separadas por coma, como escribe el cliente)",
                             value=(m or {}).get("palabras_clave", ""), height=70)
        e_nc = st.text_input("No confundir con (motivo parecido y en qué se distingue)",
                             value=(m or {}).get("no_confundir", ""))
        e_act = st.checkbox("Activo", value=(m or {}).get("activo", True))
        guardar = st.form_submit_button("💾 Guardar", type="primary")
    if guardar:
        area_final = e_area_otra.strip() if e_area == "(otra área…)" else e_area
        dup = next((x for x in todos if cl.clave_motivo(x["motivo"]) == cl.clave_motivo(e_mot)
                    and x.get("id") != (m or {}).get("id")), None)
        if not e_mot.strip() or not area_final:
            st.error("El motivo y el área son obligatorios.")
        elif dup:
            st.error(f"Ya existe un motivo con ese nombre: «{dup['motivo']}».")
        else:
            ok, r = dbm.guardar_clasif_motivo(
                {"motivo": e_mot, "area": area_final, "descripcion": e_desc,
                 "palabras_clave": e_pal, "no_confundir": e_nc, "activo": e_act},
                usuario["nombre_completo"], (m or {}).get("id"))
            if ok:
                invalidar_cache_clasificador()
                st.success("Guardado.")
                st.rerun()
            else:
                st.error(f"No se pudo guardar: {r}")

    # ── Admin: importar Excel ──
    with st.expander("📥 Importar / actualizar catálogo desde Excel"):
        st.caption("Columnas que se reconocen por su título (en cualquier orden): **MOTIVO DE CASO** y "
                   "**AREA** (obligatorias), **CUANDO APLICA**, **PALABRAS CLAVE** y **NO CONFUNDIR CON** "
                   "(opcionales; si no vienen, se conservan las que ya tiene el sistema). Los motivos se "
                   "comparan por nombre: si ya existe se actualiza, si no, se agrega.")
        with st.form("clf_form_import"):
            arch = st.file_uploader("Excel del catálogo (.xlsx)", type=["xlsx"],
                                    key=f"clf_up_{st.session_state.get('clf_up_key', 0)}")
            prev = st.form_submit_button("🔍 Revisar cambios")
        if prev:
            if arch is None:
                st.error("Sube el Excel primero.")
            else:
                filas, avisos, err = cl.leer_excel_catalogo(arch)
                if err:
                    st.error(err)
                    st.session_state["clf_import"] = None
                else:
                    st.session_state["clf_import"] = {"filas": filas, "avisos": avisos,
                                                      "cmp": cl.comparar_con_catalogo(filas, todos)}
        imp = st.session_state.get("clf_import")
        if imp:
            cmp_ = imp["cmp"]
            for a in imp["avisos"]:
                st.warning(a)
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Nuevos", len(cmp_["nuevos"]))
            k2.metric("Con cambios", len(cmp_["cambios"]))
            k3.metric("Sin cambios", len(cmp_["iguales"]))
            k4.metric("No vienen en el Excel", len(cmp_["faltantes"]))
            if cmp_["nuevos"]:
                st.markdown("**Se agregarán:** " + ", ".join(f["motivo"] for f in cmp_["nuevos"]))
            if cmp_["cambios"]:
                with st.expander(f"Ver los {len(cmp_['cambios'])} cambios"):
                    for c in cmp_["cambios"]:
                        st.markdown(f"**{c['actual']['motivo']}** — cambia: " + ", ".join(c["dif"].keys()))
            baja_falt = False
            if cmp_["faltantes"]:
                st.markdown("**Activos en el sistema que no vienen en el Excel:** "
                            + ", ".join(m["motivo"] for m in cmp_["faltantes"]))
                baja_falt = st.checkbox("Dar de baja los que no vienen en el Excel (se ocultan, no se borran)",
                                        key="clf_baja_falt")
            b1, b2 = st.columns(2)
            total = len(cmp_["nuevos"]) + len(cmp_["cambios"]) + (len(cmp_["faltantes"]) if baja_falt else 0)
            if b1.button(f"✅ Aplicar {total} cambio(s)", type="primary", disabled=total == 0, key="clf_aplicar"):
                errores, hechos = [], 0
                barra = st.progress(0.0, text="Aplicando…")
                tareas = ([("nuevo", f, None) for f in cmp_["nuevos"]] +
                          [("cambio", c["nuevo"], c["actual"]["id"]) for c in cmp_["cambios"]] +
                          ([("baja", m, m["id"]) for m in cmp_["faltantes"]] if baja_falt else []))
                for i, (t, datos, mid) in enumerate(tareas, 1):
                    d = {"activo": False} if t == "baja" else {**{k: v for k, v in datos.items() if k != "fila_excel"}, "activo": True}
                    ok, r = dbm.guardar_clasif_motivo(d, usuario["nombre_completo"], mid)
                    hechos += ok
                    if not ok:
                        errores.append(f"{datos.get('motivo')}: {r}")
                    barra.progress(i / len(tareas), text=f"Aplicando… {i}/{len(tareas)}")
                invalidar_cache_clasificador()
                st.session_state["clf_import"] = None
                st.session_state["clf_up_key"] = st.session_state.get("clf_up_key", 0) + 1
                st.session_state["clf_import_msg"] = (hechos, errores)
                st.rerun()
            if b2.button("Cancelar", key="clf_cancel_imp"):
                st.session_state["clf_import"] = None
                st.rerun()
        if st.session_state.get("clf_import_msg"):
            hechos, errores = st.session_state.pop("clf_import_msg")
            st.success(f"Listo: se aplicaron {hechos} cambio(s).")
            for e in errores:
                st.error(e)


# ── 💡 Sugerencias ──────────────────────────────────────────────
def _tab_sugerencias(usuario, es_admin):
    activos = sorted(_activos(), key=lambda x: cl.normalizar(x["motivo"]))
    areas = sorted({m.get("area") or "—" for m in activos})
    if es_admin:
        _panel_admin_sugerencias(usuario, areas)
        st.markdown("---")

    st.markdown("<div class='sec-hdr'>💡 Enviar una sugerencia</div>", unsafe_allow_html=True)
    if st.session_state.get("clf_sug_ok"):
        st.success(st.session_state.pop("clf_sug_ok"))
    tipo_lbl = st.radio("¿Qué quieres sugerir?", list(TIPOS_SUG.values()), key="clf_sug_tipo", horizontal=True)
    tipo = next(k for k, v in TIPOS_SUG.items() if v == tipo_lbl)
    nombres = [f"{m['motivo']}  ·  {m.get('area')}" for m in activos]
    with st.form(f"clf_form_sug_{tipo}_{st.session_state.get('clf_sug_n', 0)}"):
        m_sel, prop = None, {}
        if tipo != "nuevo":
            idx = st.selectbox("Motivo al que aplica *", range(len(nombres)), format_func=lambda i: nombres[i]) \
                if nombres else None
            m_sel = activos[idx] if idx is not None else None
        if tipo in ("nuevo", "corregir"):
            ayuda = " (deja vacío lo que no cambia)" if tipo == "corregir" else ""
            prop["motivo"] = st.text_input("Nombre del motivo" + (" *" if tipo == "nuevo" else ayuda))
            area = st.selectbox("Área", ["(sin cambio)" if tipo == "corregir" else "(elige)"] + areas + ["(otra área…)"])
            area_otra = st.text_input("Si elegiste «otra área», escríbela aquí")
            prop["descripcion"] = st.text_area("Cuándo aplica" + ayuda, height=90)
            prop["palabras_clave"] = st.text_input("Palabras clave (separadas por coma)")
            prop["no_confundir"] = st.text_input("No confundir con (motivo parecido y en qué se distingue)")
        elif tipo == "palabras":
            prop["palabras_clave"] = st.text_input("Palabras que usan los clientes para este caso (separadas por coma) *")
            prop["no_confundir"] = st.text_input("Diferenciador: ¿con qué motivo se confunde y en qué se distingue?")
        comentario = st.text_area("¿Por qué? / comentario *", height=70)
        enviar = st.form_submit_button("📨 Enviar sugerencia", type="primary")
    if enviar:
        if tipo in ("nuevo", "corregir"):
            prop["area"] = area_otra.strip() if area == "(otra área…)" else ("" if area.startswith("(") else area)
        prop = {k: v.strip() for k, v in prop.items() if str(v).strip()}
        err = None
        if not comentario.strip():
            err = "Escribe el comentario o la razón de la sugerencia."
        elif tipo != "nuevo" and not m_sel:
            err = "Elige el motivo al que aplica."
        elif tipo == "nuevo" and (not prop.get("motivo") or not prop.get("area")):
            err = "Para un motivo nuevo, el nombre y el área son obligatorios."
        elif tipo == "nuevo" and any(cl.clave_motivo(m["motivo"]) == cl.clave_motivo(prop["motivo"]) for m in _motivos_todos()):
            err = "Ya existe un motivo con ese nombre (puede estar dado de baja). Usa «Corregir un motivo existente»."
        elif tipo == "corregir" and not prop:
            err = "Indica al menos un dato a corregir."
        elif tipo == "palabras" and not prop.get("palabras_clave") and not prop.get("no_confundir"):
            err = "Escribe palabras clave o el diferenciador."
        if err:
            st.error(err)
        else:
            ok, r = dbm.crear_clasif_sugerencia(
                tipo, prop, comentario.strip(), usuario["id"], usuario["nombre_completo"],
                (m_sel or {}).get("id"), (m_sel or {}).get("motivo") or prop.get("motivo", ""))
            if ok:
                _sug_pendientes.clear()
                st.session_state["clf_sug_ok"] = "📨 Sugerencia enviada. El admin la revisará."
                st.session_state["clf_sug_n"] = st.session_state.get("clf_sug_n", 0) + 1  # limpia el formulario
                st.rerun()
            else:
                st.error(f"No se pudo enviar: {r}")

    mias = dbm.obtener_clasif_sugerencias(solicitante_id=usuario["id"], limite=20)
    if mias:
        st.markdown("<div class='sec-hdr'>📨 Mis sugerencias</div>", unsafe_allow_html=True)
        ico = {"pendiente": "⏳", "aprobada": "✅", "rechazada": "❌"}
        st.dataframe(pd.DataFrame([{
            "Estado": f"{ico.get(s['estado'], '')} {s['estado']}",
            "Tipo": TIPOS_SUG.get(s["tipo"], s["tipo"]),
            "Motivo": s.get("motivo_nombre") or "",
            "Comentario": s.get("comentario") or "",
            "Motivo de rechazo": s.get("motivo_rechazo") or "",
        } for s in mias]), hide_index=True, width='stretch')


def _panel_admin_sugerencias(usuario, areas):
    pend = _sug_pendientes()
    st.markdown(f"<div class='admin-hdr'>🔔 Sugerencias pendientes ({len(pend)})</div>", unsafe_allow_html=True)
    if not pend:
        st.caption("No hay sugerencias pendientes.")
        return
    todos = {m["id"]: m for m in _motivos_todos()}
    for s in pend:
        prop = s.get("propuesta") or {}
        actual = todos.get(s.get("motivo_id")) or {}
        titulo = f"{TIPOS_SUG.get(s['tipo'], s['tipo'])} — {s.get('motivo_nombre') or prop.get('motivo') or ''} · por {s.get('solicitante_nombre')}"
        with st.expander(titulo, expanded=len(pend) <= 3):
            st.caption(f"Comentario: {s.get('comentario') or '—'}")
            with st.form(f"clf_form_res_{s['id']}"):
                final = dict(prop)
                if s["tipo"] in ("nuevo", "corregir"):
                    if s["tipo"] == "corregir":
                        st.caption("Vacío = no se cambia ese dato. Puedes ajustar el texto antes de aprobar.")
                    for campo, lbl in (("motivo", "Motivo"), ("area", "Área"), ("descripcion", "Cuándo aplica"),
                                       ("palabras_clave", "Palabras clave"), ("no_confundir", "No confundir con")):
                        ayuda = f"Actual: {actual.get(campo) or '—'}" if actual else None
                        if campo == "descripcion":
                            final[campo] = st.text_area(lbl, value=prop.get(campo, ""), help=ayuda, height=80)
                        else:
                            final[campo] = st.text_input(lbl, value=prop.get(campo, ""), help=ayuda)
                elif s["tipo"] == "palabras":
                    st.caption(f"Palabras actuales: {actual.get('palabras_clave') or '—'}")
                    final["palabras_clave"] = st.text_input("Palabras a agregar (puedes quitar las que no sirvan)",
                                                            value=prop.get("palabras_clave", ""))
                    final["no_confundir"] = st.text_input("Diferenciador a agregar", value=prop.get("no_confundir", ""))
                else:
                    st.markdown(f"Se dará de baja **{actual.get('motivo') or s.get('motivo_nombre')}** "
                                f"({actual.get('area') or '—'}). Se oculta, no se borra.")
                motivo_r = st.text_input("Motivo de rechazo (obligatorio solo si rechazas)")
                a1, a2 = st.columns(2)
                aprobar = a1.form_submit_button("✅ Aprobar", type="primary")
                rechazar = a2.form_submit_button("❌ Rechazar")
            if aprobar or rechazar:
                if rechazar and not motivo_r.strip():
                    st.warning("Escribe el motivo del rechazo.")
                else:
                    final = {k: v.strip() for k, v in final.items() if str(v or "").strip()}
                    ok, err = dbm.resolver_clasif_sugerencia(s, bool(aprobar), usuario["nombre_completo"],
                                                             motivo_r.strip(), final)
                    if ok:
                        invalidar_cache_clasificador()
                        st.rerun()
                    else:
                        st.error(f"No se pudo resolver: {err}")


_CSS = """
<style>
.clf-cab{display:flex;align-items:flex-end;gap:18px;margin:2px 0 14px 0;flex-wrap:wrap;
  border-bottom:4px solid #E65100;padding-left:6px}
.clf-masc{width:190px !important;max-width:40vw !important;height:auto !important;object-fit:fill !important;
  image-rendering:pixelated;image-rendering:crisp-edges;
  flex:0 0 auto;display:block;margin-bottom:-1px}
.clf-globo{position:relative;border:3px solid #E65100;border-radius:14px;padding:10px 14px;
  background:#FFF3E0;color:#3E2723;font-size:14px;max-width:560px;margin-bottom:22px}
.clf-globo:before{content:"";position:absolute;left:-13px;top:22px;border:11px solid transparent;
  border-right-color:#E65100;border-left:0}
.clf-globo b{color:#BF360C;font-size:16px}
.clf-area{display:inline-block;background:#E65100;color:#fff;border-radius:6px;padding:2px 8px;
  font-size:12px;font-weight:600;white-space:nowrap}
.clf-chip{display:inline-block;font-family:monospace;font-size:11px;padding:1px 7px;margin:0 4px 4px 0;
  border-radius:4px;border:1px solid rgba(128,128,128,.4);opacity:.85}
.clf-nc{font-size:13px;border-left:3px solid #E65100;padding:2px 8px;margin:2px 0 6px 0;opacity:.9}
.clf-iso{flex:1 1 300px;min-width:0;height:124px;position:relative;overflow:hidden}.clf-iso-in{position:absolute;right:0;bottom:0;width:832px;height:124px;background:url(data:image/png;base64,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) no-repeat 0 0/832px 124px;image-rendering:pixelated}.clf-iso-grua{position:absolute;left:354px;top:4px;width:124px;height:116px;background:url(data:image/png;base64,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) no-repeat 0 0/124px 8352px;image-rendering:pixelated;animation:clfGrua 9s steps(72) infinite}@keyframes clfGrua{to{background-position:0 -8352px}}@media (prefers-reduced-motion: reduce){.clf-iso-grua{animation:none}}@media (max-width: 900px){.clf-iso{display:none}}
</style>
"""


# Escena isométrica pixel art (patio visto desde lejos + grúa RTG naranja animada).
# La imagen fija y la hoja de cuadros de la grúa van en el CSS; se generan con un script.
_ESCENA_HTML = "<div class='clf-iso' aria-hidden='true'><div class='clf-iso-in'><div class='clf-iso-grua'></div></div></div>"
