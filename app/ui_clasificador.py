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
</style>
"""
