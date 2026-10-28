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
# Tipos que solo se muestran (no se eligen en el formulario de Sugerencias)
TIPOS_SUG_TODOS = {**TIPOS_SUG, "reclasificar": "🔁 Correo sin motivo correcto"}

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
            asunto = st.text_input("Asunto del correo (opcional, pesa más)", key="clf_asunto",
                                   placeholder="Ej.: Sesión bloqueada")
            texto = st.text_area("Pega el cuerpo del correo", height=200,
                                 key="clf_texto",
                                 placeholder="Ej.: Hola, no puedo entrar al portal ISCS, me sale que mi "
                                             "sesión está bloqueada por adeudo…")
            ok = st.form_submit_button("🔍 Sugerir motivo", type="primary")
        if ok:
            st.session_state["clf_resultado"] = (cl.clasificar(texto, _indice(), top=3, asunto=asunto)
                                                 if (texto.strip() or asunto.strip()) else None)
            st.session_state["clf_texto_usado"] = (asunto + "\n" + cl.limpiar_correo(texto)).strip()
            st.session_state["clf_confirmado"] = None
        st.caption("🔒 El correo no se guarda. Si confirmas un motivo, solo se envían al admin "
                   "palabras clave útiles (sin nombres, RFC, contenedores ni números). La firma y los "
                   "correos anteriores del hilo se ignoran solos.")
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
            h1.markdown(f"**{i + 1}. {_esc(m['motivo'])}**" + ("  ·  ⭐ idea principal" if i == 0 else ""))
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
    # ── Opción 4: dejar como «Otros» ──
    with st.container(border=True):
        o1, o2 = st.columns([4, 1])
        o1.markdown("**4. Otros**  \nNinguna aplica y no hace falta un tipo nuevo: se queda como «Otros».")
        o2.markdown("<span class='clf-area'>Otros</span>", unsafe_allow_html=True)
        if st.button("📂 Dejar como «Otros»", key="clf_otros"):
            otros = next((x for x in _activos() if cl.clave_motivo(x["motivo"]) == "otros"),
                         {"motivo": "Otros", "area": "Otros"})
            st.session_state["clf_confirmado"] = dict(otros, _msg="")
    # ── Opción 5: sugerir otro tipo de caso distinto ──
    with st.container(border=True):
        st.markdown("**5. Sugerir otro tipo de caso distinto**  \nSi ninguna de las 3 es correcta, "
                    "explica por qué; el admin lo revisa y con eso aprende el clasificador.")
        nombres = ["— No sé / no está en el catálogo —"] + [
            f"{x['motivo']}  ·  {x.get('area')}" for x in sorted(_activos(), key=lambda y: cl.normalizar(y["motivo"]))]
        with st.form(f"clf_form_otro_{st.session_state.get('clf_otro_n', 0)}"):
            por_que = st.text_area("¿Por qué ninguna de las 3 opciones es la correcta? *", height=80)
            elegido = st.selectbox("Si sabes cuál es el tipo de caso correcto, elígelo (opcional)", nombres)
            enviar_otro = st.form_submit_button("📨 Enviar al admin")
        if enviar_otro:
            if not por_que.strip():
                st.error("Escribe por qué ninguna de las 3 opciones es la correcta.")
            else:
                orden = sorted(_activos(), key=lambda y: cl.normalizar(y["motivo"]))
                m_ok = None if elegido == nombres[0] else orden[nombres.index(elegido) - 1]
                palabras = cl.extraer_palabras_clave(st.session_state.get("clf_texto_usado", ""))
                prop = {"palabras_clave": ", ".join(palabras),
                        "sugeridos_sistema": " | ".join(x["motivo"]["motivo"] for x in R["items"])}
                if m_ok:
                    prop["motivo_id"] = m_ok["id"]
                ok_o, err_o = dbm.crear_clasif_sugerencia(
                    "reclasificar", prop, por_que.strip(), usuario["id"], usuario["nombre_completo"],
                    (m_ok or {}).get("id"), (m_ok or {}).get("motivo") or "(sin elegir)")
                if ok_o:
                    _sug_pendientes.clear()
                    st.session_state["clf_otro_n"] = st.session_state.get("clf_otro_n", 0) + 1
                    st.session_state["clf_confirmado"] = {
                        "motivo": (m_ok or {}).get("motivo") or "pendiente de revisión",
                        "area": (m_ok or {}).get("area") or "—",
                        "_msg": "Se envió al admin para revisión. ¡Gracias, así aprende el clasificador!"}
                    st.rerun()
                else:
                    st.error(f"No se pudo enviar: {err_o}")

    # ── Otros temas en el mismo correo ──
    if R.get("temas"):
        st.markdown("<div class='sec-hdr'>🧩 El correo también menciona…</div>", unsafe_allow_html=True)
        st.caption("Detectado oración por oración. Si el cliente pide varias cosas, puede requerir "
                   "más de un caso o área.")
        for tm in R["temas"]:
            mm = tm["motivo"]
            st.markdown(f"- **{_esc(mm['motivo'])}** <span class='clf-area'>{_esc(mm.get('area'))}</span> — "
                        f"<i>«{_esc(tm['oracion'][:160])}»</i>", unsafe_allow_html=True)

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
            "Tipo": TIPOS_SUG_TODOS.get(s["tipo"], s["tipo"]),
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
        titulo = f"{TIPOS_SUG_TODOS.get(s['tipo'], s['tipo'])} — {s.get('motivo_nombre') or prop.get('motivo') or ''} · por {s.get('solicitante_nombre')}"
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
                elif s["tipo"] == "reclasificar":
                    st.caption(f"El sistema había sugerido: {prop.get('sugeridos_sistema') or '—'}")
                    orden = sorted(_motivos_todos(), key=lambda y: cl.normalizar(y["motivo"]))
                    ops = [f"{x['motivo']}  ·  {x.get('area')}" for x in orden]
                    pre = next((i for i, x in enumerate(orden) if x.get("id") == prop.get("motivo_id")), None)
                    sel = st.selectbox("Tipo de caso correcto * (si no existe, créalo primero en 📚 Catálogo)",
                                       range(len(ops)), format_func=lambda i: ops[i], index=pre,
                                       placeholder="Elige el tipo de caso correcto")
                    final["motivo_id"] = orden[sel]["id"] if sel is not None else ""
                    final["palabras_clave"] = st.text_input("Palabras del correo a agregar a ese tipo de caso "
                                                            "(quita las que no sirvan)",
                                                            value=prop.get("palabras_clave", ""))
                    final.pop("sugeridos_sistema", None)
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
                elif aprobar and s["tipo"] == "reclasificar" and not final.get("motivo_id"):
                    st.warning("Elige el tipo de caso correcto antes de aprobar.")
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
