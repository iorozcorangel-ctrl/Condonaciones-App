"""
================================================================
  CLASIFICADOR DE CASOS — motor de búsqueda y clasificación de texto
  (sin IA ni servicios externos: palabras clave + raíces + rareza)

  - El catálogo (motivos) vive en Supabase (tabla clasif_motivos) y lo
    administra solo el admin. Este archivo no habla con la base de datos.
  - Pesos: nombre del motivo y palabras clave = 3, "cuándo aplica" = 1.2,
    área = 0.6. Las palabras raras (que salen en pocos motivos) valen más.
================================================================
"""
import io
import re
import unicodedata

import pandas as pd

# Palabras de relleno que no ayudan a clasificar
STOP = set((
    "a al algo algun alguna ante antes aqui asi aun bien buen buenas buenos como con contra cual cuales "
    "cuando de del desde donde dos el ella ellas ellos en entre era es esa ese eso esta estan estar este "
    "esto estos estamos fue gracias ha hay hola la las le les lo los mas me mi mis muy nada ni no nos "
    "nosotros o otra otro para pero poco por porque pues que quien se sea ser si sin sobre solo su sus tal "
    "tambien tanto te tiene tienen todo todos tu un una uno unos usted ustedes y ya yo favor saludos dia "
    "dias tardes cordial apoyo ayuda quisiera quiero queremos necesito necesitamos poder puedo pueden "
    "podrian solicito solicitamos etc caso casos cliente clientes cmsa escribo escribe sale salir saber "
    "paso mes pasado noches estimado estimados estimada equipo correo adjunto adjunta anexo anexa mismo "
    "esto ahora tambien"
).split())

PESOS = {"motivo": 3.0, "palabras_clave": 3.0, "descripcion": 1.2, "area": 0.6}


def normalizar(texto) -> str:
    """minúsculas, sin acentos, solo letras/números separados por un espacio."""
    t = unicodedata.normalize("NFD", str(texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def clave_motivo(nombre) -> str:
    """Llave para comparar nombres de motivo (ignora acentos, mayúsculas y espacios)."""
    return normalizar(nombre)


def raiz(p: str) -> str:
    """Raíz simple: quita plurales y deja 5 letras (factura/facturas/facturación → 'factu')."""
    if len(p) > 4 and p.endswith("es"):
        p = p[:-2]
    elif len(p) > 3 and p.endswith("s"):
        p = p[:-1]
    return p[:5] if len(p) > 5 else p


def raices(texto) -> list:
    return [raiz(p) for p in normalizar(texto).split()
            if len(p) > 2 and p not in STOP and not p.isdigit()]


# ── Índice ─────────────────────────────────────────────────────
def construir_indice(motivos: list) -> dict:
    """motivos: lista de dicts con motivo, area, descripcion, palabras_clave."""
    import math
    docs = []
    for m in motivos:
        pesos = {}
        for campo, w in PESOS.items():
            for r in raices(m.get(campo) or ""):
                pesos[r] = max(pesos.get(r, 0), w)
        # frases de 2+ palabras en las palabras clave ("no puedo entrar", "sesion bloqueada"):
        # si aparecen completas en el correo valen extra
        frases = [normalizar(f) for f in str(m.get("palabras_clave") or "").split(",")
                  if len(normalizar(f).split()) >= 2]
        docs.append((m, pesos, frases))
    df = {}
    for _, pesos, _ in docs:
        for r in pesos:
            df[r] = df.get(r, 0) + 1
    n = max(len(docs), 1)
    idf = {r: math.log(1 + n / c) for r, c in df.items()}
    return {"docs": docs, "idf": idf}


# ── Limpieza del correo: quitar hilo anterior, firma y avisos legales ──
_CORTES = [
    r"^\s*(de|from|enviado el|sent|para|to)\s*:",          # encabezados de correos citados
    r"^\s*-{2,}\s*(mensaje original|original message)",
    r"^\s*el .{5,80} escribio\s*:",                        # "El lun, ... escribió:"
    r"^\s*on .{5,80} wrote\s*:",
    r"^\s*(enviado desde|sent from) ",
    r"^\s*(este correo|este mensaje|la informacion contenida|aviso de confidencialidad|confidencial)",
]
_DESPEDIDAS = r"^\s*(saludos|saludo|atentamente|quedo atento|quedo atenta|quedo en espera|gracias de antemano|cordialmente|un saludo|best regards|regards)\b"


def limpiar_correo(texto: str) -> str:
    """Deja solo el mensaje nuevo: corta en el primer correo citado o aviso legal,
    y en la despedida (lo que sigue suele ser la firma)."""
    lineas = str(texto or "").splitlines()
    salida = []
    for ln in lineas:
        n = normalizar(ln) if ln.strip() else ""
        bruto = unicodedata.normalize("NFD", ln.lower())
        bruto = "".join(c for c in bruto if unicodedata.category(c) != "Mn")
        if any(re.search(p, bruto) for p in _CORTES):
            break
        if re.search(_DESPEDIDAS, bruto) and len(n.split()) <= 6:
            break
        salida.append(ln)
    limpio = "\n".join(salida).strip()
    return limpio or str(texto or "")


def oraciones(texto: str) -> list:
    partes = re.split(r"(?<=[.!?¿¡])\s+|\n+", str(texto or ""))
    return [p.strip() for p in partes if len(normalizar(p).split()) >= 3]


def _consulta_ponderada(texto: str, asunto: str = "") -> dict:
    """Raíz → peso. El asunto pesa 2, las 2 primeras oraciones 1.5 y el resto 1
    (la idea principal casi siempre va en el asunto o al inicio)."""
    q = {}
    for r in raices(asunto):
        q[r] = max(q.get(r, 0), 2.0)
    for i, o in enumerate(oraciones(texto)):
        w = 1.5 if i < 2 else 1.0
        for r in raices(o):
            q[r] = max(q.get(r, 0), w)
    if not q:                                   # texto sin oraciones "largas"
        for r in raices(texto):
            q[r] = max(q.get(r, 0), 1.0)
    return q


def _puntuar(q: dict, texto_norm: str, indice: dict) -> list:
    idf = indice["idf"]
    res = []
    for m, pesos, frases in indice["docs"]:
        s, hits = 0.0, []
        for r, wq in q.items():
            if r in pesos:
                s += idf[r] * pesos[r] * wq
                hits.append(r)
        for f in frases:
            if f and f" {f} " in f" {texto_norm} ":
                s += 6.0
                hits.append(f"«{f}»")
        if s > 0:
            res.append({"motivo": m, "score": s, "hits": hits})
    res.sort(key=lambda x: -x["score"])
    return res


def clasificar(texto: str, indice: dict, top: int = 3, asunto: str = "", limpiar: bool = True) -> dict:
    """
    Regresa {"nivel": alta|media|baja, "empate": bool, "items": [...], "temas": [...]}.
    Cada item: motivo (dict original), score, rel (% frente al 1.º), hits (palabras).
    "temas": otros temas que aparecen en oraciones sueltas del correo (correos con varias peticiones).
    """
    vacio = {"nivel": "baja", "empate": False, "items": [], "temas": []}
    if not indice.get("docs"):
        return vacio
    cuerpo = limpiar_correo(texto) if limpiar else str(texto or "")
    q = _consulta_ponderada(cuerpo, asunto)
    if not q:
        return vacio
    res = _puntuar(q, normalizar(asunto + " " + cuerpo), indice)
    if not res:
        return vacio
    s1 = res[0]["score"]
    s2 = res[1]["score"] if len(res) > 1 else 0
    margen = (s1 - s2) / s1 if s1 else 0
    nivel = "alta" if (s1 >= 25 and margen >= 0.35) else "media" if (s1 >= 14 and margen >= 0.15) else "baja"
    items = [dict(x, rel=round(100 * x["score"] / s1)) for x in res[:top]]
    return {"nivel": nivel, "empate": len(res) > 1 and margen < 0.05, "items": items,
            "temas": temas_del_correo(cuerpo, indice, excluir={clave_motivo(items[0]["motivo"]["motivo"])})}


def temas_del_correo(cuerpo: str, indice: dict, excluir: set = None, minimo: float = 12.0, maximo: int = 3) -> list:
    """Clasifica cada oración por separado para detectar peticiones adicionales.
    Regresa [{motivo, score, oracion}] de temas distintos al principal, con puntaje suficiente."""
    excluir = set(excluir or set())
    temas = {}
    for o in oraciones(cuerpo):
        q = {r: 1.0 for r in raices(o)}
        r = _puntuar(q, normalizar(o), indice)
        if not r or r[0]["score"] < minimo:
            continue
        # la oración debe apuntar claramente a un motivo (no empate)
        if len(r) > 1 and r[1]["score"] > r[0]["score"] * 0.85:
            continue
        k = clave_motivo(r[0]["motivo"]["motivo"])
        if k in excluir:
            continue
        if k not in temas or r[0]["score"] > temas[k]["score"]:
            temas[k] = {"motivo": r[0]["motivo"], "score": r[0]["score"], "oracion": o}
    return sorted(temas.values(), key=lambda x: -x["score"])[:maximo]


def buscar(texto: str, motivos: list, indice: dict, limite: int = 15) -> list:
    """Buscador: primero coincidencias de texto exacto (nombre/área/descripción), luego por relevancia."""
    t = normalizar(texto)
    if not t:
        return []
    directos = [m for m in motivos
                if t in normalizar(m.get("motivo")) or t in normalizar(m.get("area"))
                or t in normalizar(m.get("palabras_clave"))]
    por_rel = [x["motivo"] for x in clasificar(texto, indice, top=limite)["items"]]
    vistos, out = set(), []
    for m in directos + por_rel:
        k = clave_motivo(m.get("motivo"))
        if k not in vistos:
            vistos.add(k)
            out.append(m)
    return out[:limite]


# ── Privacidad: del correo solo se guardan palabras útiles ───────
_PATRONES_SENSIBLES = [
    r"\S+@\S+",                              # correos
    r"\b[a-zA-Z]{4}\s?\d{7}\b",              # contenedores
    r"\b[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}\b",     # RFC
    r"https?://\S+",                         # ligas
    r"\S*\d\S*",                             # cualquier cosa con números (folios, teléfonos, montos)
]


def extraer_palabras_clave(texto: str, maximo: int = 15) -> list:
    """Palabras útiles del correo para sugerir al admin, sin datos del cliente.
    Quita correos, contenedores, RFC, números, palabras de relleno y nombres propios
    a mitad de oración (palabras que empiezan con mayúscula)."""
    t = str(texto or "")
    for p in _PATRONES_SENSIBLES:
        t = re.sub(p, " ", t)
    palabras = []
    for oracion in re.split(r"[.!?\n]+", t):
        tokens = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", oracion)
        for i, tok in enumerate(tokens):
            if i > 0 and tok[0].isupper() and not tok.isupper():
                continue                       # probable nombre propio
            n = normalizar(tok)
            if len(n) > 3 and n not in STOP and n not in palabras:
                palabras.append(n)
    return palabras[:maximo]


def unir_palabras(actuales: str, nuevas) -> str:
    """Une listas de palabras clave separadas por coma, sin repetir."""
    lista = [p.strip() for p in str(actuales or "").split(",") if p.strip()]
    vistos = {normalizar(p) for p in lista}
    for p in (nuevas if isinstance(nuevas, (list, tuple)) else str(nuevas or "").split(",")):
        p = str(p).strip()
        if p and normalizar(p) not in vistos:
            lista.append(p)
            vistos.add(normalizar(p))
    return ", ".join(lista)


# ── Excel: leer (importar) y escribir (exportar) ─────────────────
_ALIAS_COL = {
    "motivo": ["motivo de caso", "motivo", "tipo de caso"],
    "area": ["area"],
    "descripcion": ["cuando aplica esta categorizacion", "cuando aplica", "descripcion"],
    "palabras_clave": ["palabras clave", "palabras", "sinonimos"],
    "no_confundir": ["no confundir con", "no confundir", "diferenciador"],
}


def leer_excel_catalogo(archivo):
    """
    Lee el Excel del catálogo buscando los encabezados por su TEXTO (en cualquier
    columna y en las primeras 10 filas). Obligatorias: MOTIVO DE CASO y AREA.
    Regresa (filas, avisos, error).
    """
    try:
        crudo = pd.read_excel(archivo, header=None, dtype=object)
    except Exception as e:
        return [], [], f"No se pudo leer el Excel: {e}"
    fila_enc, mapa = None, {}
    for i in range(min(10, len(crudo))):
        celdas = {j: normalizar(v) for j, v in enumerate(crudo.iloc[i].tolist())}
        m = {}
        for campo, alias in _ALIAS_COL.items():
            for j, txt in celdas.items():
                if txt and any(txt == a or txt.startswith(a) for a in alias):
                    m.setdefault(campo, j)
        if "motivo" in m and "area" in m:
            fila_enc, mapa = i, m
            break
    if fila_enc is None:
        return [], [], ("No encontré los encabezados. El Excel debe tener al menos las columnas "
                        "«MOTIVO DE CASO» y «AREA» (y de preferencia «CUANDO APLICA»).")
    filas, avisos, vistos = [], [], {}

    def celda(r, campo):
        j = mapa.get(campo)
        if j is None:
            return None
        v = crudo.iat[r, j]
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        return re.sub(r"\s+", " ", str(v)).strip()

    for r in range(fila_enc + 1, len(crudo)):
        motivo = celda(r, "motivo")
        if not motivo:
            continue
        area = celda(r, "area") or ""
        desc = celda(r, "descripcion") or ""
        desc = re.sub(r"^\*\s*", "", desc)
        fila = {"fila_excel": r + 1, "motivo": motivo, "area": area, "descripcion": desc}
        for opc in ("palabras_clave", "no_confundir"):
            if opc in mapa:
                fila[opc] = celda(r, opc) or ""
        if not area:
            avisos.append(f"Fila {r + 1}: «{motivo}» no tiene AREA.")
        k = clave_motivo(motivo)
        if k in vistos:
            avisos.append(f"Fila {r + 1}: «{motivo}» está repetido (fila {vistos[k]}); se usa la última.")
            filas = [f for f in filas if clave_motivo(f["motivo"]) != k]
        vistos[k] = r + 1
        filas.append(fila)
    if not filas:
        return [], avisos, "El Excel no trae motivos debajo de los encabezados."
    return filas, avisos, None


def comparar_con_catalogo(filas: list, actuales: list) -> dict:
    """Clasifica las filas del Excel en nuevos / actualizados / iguales, y lista
    los motivos activos del sistema que no vienen en el Excel."""
    por_clave = {clave_motivo(m["motivo"]): m for m in actuales}
    nuevos, cambios, iguales = [], [], []
    for f in filas:
        m = por_clave.get(clave_motivo(f["motivo"]))
        if m is None:
            nuevos.append(f)
            continue
        dif = {}
        for campo in ("motivo", "area", "descripcion", "palabras_clave", "no_confundir"):
            if campo in f and (f[campo] or "") != (m.get(campo) or ""):
                dif[campo] = (m.get(campo) or "", f[campo] or "")
        if not m.get("activo", True):
            dif["activo"] = (False, True)
        (cambios if dif else iguales).append({"actual": m, "nuevo": f, "dif": dif})
    claves_excel = {clave_motivo(f["motivo"]) for f in filas}
    faltantes = [m for m in actuales if m.get("activo", True) and clave_motivo(m["motivo"]) not in claves_excel]
    return {"nuevos": nuevos, "cambios": cambios, "iguales": iguales, "faltantes": faltantes}


def exportar_excel(motivos: list) -> bytes:
    """Excel del catálogo actual (mismo formato que se importa) para editarlo y volver a subirlo."""
    df = pd.DataFrame([{
        "MOTIVO DE CASO": m.get("motivo", ""),
        "AREA": m.get("area", ""),
        "CUANDO APLICA ESTA CATEGORIZACION?": m.get("descripcion", ""),
        "PALABRAS CLAVE": m.get("palabras_clave", "") or "",
        "NO CONFUNDIR CON": m.get("no_confundir", "") or "",
        "ACTIVO": "SI" if m.get("activo", True) else "NO",
    } for m in sorted(motivos, key=lambda x: normalizar(x.get("motivo")))])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Catalogo")
        ws = w.sheets["Catalogo"]
        for col, ancho in zip("ABCDEF", (42, 24, 90, 45, 45, 9)):
            ws.column_dimensions[col].width = ancho
        ws.freeze_panes = "A2"
    return buf.getvalue()


# Mascota de la cintura para arriba (pixel art 61×53, se escala en pantalla con image-rendering: pixelated)
MASCOTA_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAD0AAAA1CAYAAADyMeOEAAADfUlEQVR42uWZvWsbMRTA3x1H9oIHh8KZpG4DpRQ3FHtuMaVj"
    "piaDZ0+ZHf8JvsyZMnUIpfZQMpVQTDsrFNeEEnA/UmII8RDo7sUdUh06nU4nnXQ6JXlg7EPvzvrpPT299w7gDoqj4yHlmr9I"
    "GpuNp86tgSZBp8e/EvX8etW6BXCywtKg33+eR66fPKwkLkDR8J4sMM+qaYLv9evVRZHgrilgGp4XB6yA1glsA7hbBHDR4J4p"
    "4KvNpch1qT8PwU3vcdekhUv9eQhbpMVd0y5tg6t7JsFoF78R57Sqa9sirg2ubdrFvbSCoQgh55NHVHeKtKyI+PWqdnAX7qB4"
    "SVWSDcKq1LSVlrbt6bybEEIPLNf8RWOnAQAAKECRWtqvVwGPYRHRwXpFlJhSe5qGwccMCpCUjvWdE2xlFgyrK5Kmw/IK09Z2"
    "sgJXVh8BAMD52Y/E+1k6NoArH1kYTFXnVubeMllY3hHdE4nYeYvs/6AAlJoONzIja+w0lHILR9TSeUVvGbmYXML9tWXlAOjK"
    "rC75toIFI6KjIhj4YnKpZHFX1q1oKBpGREdVSGvnGr2frT2Ab5PfMSgWjIiOqfqbNSaUnNDgRQsKEJC1wP7uQTjW7rRCuHLN"
    "X7DGpNwbAx/+fRF+6MnQcrg10HpNAluRnOCUlZTloKL1WsdW8dIyHxRALEnZuPdFOtE43BrAxvs3ifepjmuN3tfg6mVh2oRV"
    "x+lYxDvKrMm9swY0WsjApQSd5OZFA8/GUwdbdDgccvWbzaa8pTG4iXNXFDgJSnv0/v9qNRO4rpZRbqUlKzjgYgKDixwjNOho"
    "ZZr4XiuPxn5maJyZ+fUqkOB0hcWSz8Nu+Ptls6cdYDaeOu1OK4zUX49GMDo5BbzPB5/exjzEEwXmyWhlCut//AhgmrBf2/pQ"
    "rvnSDQIy7Xz+ej0WxenneTLAtLVVpdSfw9XmEpT68zBOoACFRYIoPNYn59rutOxsF2FrX3/7sfiATwveAiTNkyxIhKB5wLqt"
    "Ldo7IxdAeyBLszCvbXR6diLl2hHhBEOR3IBuJUWLoGgj0dMFDADwePVpCurH3LxCppsiXE+nARctuG+mDdp2YJ6lWSmrJ+ra"
    "7z4cJY69kpwg61m97h50e9vSezmXjAwFCHrdPSPWIv+n29uOFDm87gw72iMz7SKZ6J21uOC90iEXaH/3IJaGYvkHPhxHYP6i"
    "Xz4AAAAASUVORK5CYII="
)
