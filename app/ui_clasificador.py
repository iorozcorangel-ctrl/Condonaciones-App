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
.clf-iso{flex:1 1 300px;min-width:0;height:124px;position:relative;overflow:hidden}.clf-iso-in{position:absolute;right:0;bottom:0;width:832px;height:124px;background:url(data:image/png;base64,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) no-repeat 0 0/832px 124px;image-rendering:pixelated}.clf-iso-grua{position:absolute;left:354px;top:4px;width:130px;height:120px;background:url(data:image/png;base64,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) no-repeat 0 0/130px 11520px;image-rendering:pixelated;animation:clfGrua 12s steps(96) infinite}@keyframes clfGrua{to{background-position:0 -11520px}}@media (prefers-reduced-motion: reduce){.clf-iso-grua{animation:none}}@media (max-width: 900px){.clf-iso{display:none}}
</style>
"""


# Escena isométrica pixel art (patio visto desde lejos + grúa RTG naranja que carga y
# descarga un camión en bucle).
# La imagen fija y la hoja de cuadros de la grúa van en el CSS; se generan con un script.
_ESCENA_HTML = "<div class='clf-iso' aria-hidden='true'><div class='clf-iso-in'><div class='clf-iso-grua'></div></div></div>"
