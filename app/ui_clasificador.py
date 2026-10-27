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
.clf-iso{flex:1 1 300px;min-width:0;height:124px;position:relative;overflow:hidden}.clf-iso-in{position:absolute;right:0;bottom:0;width:832px;height:124px;background:url(data:image/png;base64,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) no-repeat 0 0/832px 11904px;image-rendering:pixelated;animation:clfPatio 12s steps(96) infinite}@keyframes clfPatio{to{background-position:0 -11904px}}@media (prefers-reduced-motion: reduce){.clf-iso-in{animation:none}}@media (max-width: 900px){.clf-iso{display:none}}
</style>
"""


# Escena isométrica pixel art (patio visto desde lejos): llega un camión vacío, la grúa RTG
# naranja lo carga, el camión sigue de frente y sale; llega el siguiente… en bucle.
# La imagen fija y la hoja de cuadros de la grúa van en el CSS; se generan con un script.
_ESCENA_HTML = "<div class='clf-iso' aria-hidden='true'><div class='clf-iso-in'></div></div>"
