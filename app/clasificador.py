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
    "podrian solicito solicitamos etc caso casos cliente clientes cmsa"
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
    docs = []
    for m in motivos:
        pesos = {}
        for campo, w in PESOS.items():
            for r in raices(m.get(campo) or ""):
                pesos[r] = max(pesos.get(r, 0), w)
        docs.append((m, pesos))
    df = {}
    for _, pesos in docs:
        for r in pesos:
            df[r] = df.get(r, 0) + 1
    import math
    n = max(len(docs), 1)
    idf = {r: math.log(1 + n / c) for r, c in df.items()}
    return {"docs": docs, "idf": idf}


def clasificar(texto: str, indice: dict, top: int = 3) -> dict:
    """
    Regresa {"nivel": alta|media|baja, "empate": bool, "items": [...]}.
    Cada item: motivo (dict original), score, rel (% frente al 1.º), hits (palabras).
    """
    q = list(dict.fromkeys(raices(texto)))
    vacio = {"nivel": "baja", "empate": False, "items": []}
    if not q or not indice.get("docs"):
        return vacio
    idf = indice["idf"]
    res = []
    for m, pesos in indice["docs"]:
        s, hits = 0.0, []
        for r in q:
            if r in pesos:
                s += idf[r] * pesos[r]
                hits.append(r)
        if s > 0:
            res.append({"motivo": m, "score": s, "hits": hits})
    if not res:
        return vacio
    res.sort(key=lambda x: -x["score"])
    s1 = res[0]["score"]
    s2 = res[1]["score"] if len(res) > 1 else 0
    margen = (s1 - s2) / s1 if s1 else 0
    nivel = "alta" if (s1 >= 25 and margen >= 0.35) else "media" if (s1 >= 14 and margen >= 0.15) else "baja"
    items = [dict(x, rel=round(100 * x["score"] / s1)) for x in res[:top]]
    return {"nivel": nivel, "empate": len(res) > 1 and margen < 0.05, "items": items}


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


# Mascota (pixel art 74×78, se escala en pantalla con image-rendering: pixelated)
MASCOTA_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAEoAAABOCAYAAACHQYBnAAAEx0lEQVR42u2bvUsbYRzHf3cc7gWHSOFEm1YopViRZBNabHGU"
    "DlWKs5Ozxr+gibMgOHWQ0jgUpyJV6nylpCJFsC8WA6KD0N0lHexzPHnyvOaet8T7gmi45+7iJ7/35wKQS0qB7RsWxuMW69jl"
    "YTO41aBwOM0vv5jr4lLRW2iBDUAknO8/z9peP7o/zITmC7DIJCSe9YiEzo1LxZYPsEIfIZHAeHGtZ0HphOQTrNB3SL7AinyE"
    "dDU30PZ6sH6dwnIVs0JfLWmwfp0C8sGyQp/dzSc3jMBTke7Xt3VUVrfzTWGvuZ0r94u6gePTJ42/H5PZMOgVC5JRXCoagxVC"
    "LnPBnOz+fRBtAuHM9XyMUbi8iVGyIMsrZQAASGpJ2ywqLhUBHUOSWYPWuRy3GItRJACU0pNaorTGFwUmrIkGgMxOCApvDc36"
    "XFlVYAPS8OgDAAA4O/3BPJ+2xidYVssDBCPrmrzXM5B5dVlfpNPtbEj1PkkNtAz6+r4yL6+UtdR+gQmLMpX1VHR+cgF3x4a0"
    "JYHQ1KeI7/rSAMisySIE6fzkQotlhSZNngRBApBZk1W4VXmX9Z6M3YNvJ787QNAAyKwxlTFJV+Qd015wkrBcK6klgPeem2tb"
    "6bHF5YUUSGE8brGOGXU9BGnn79P0h/wHSO3Mb2t9jUPq2YITtTu4hmrDWl/rdGNtoC4Pm0FSg47Cc/bOgXLxuDO/DbPvXzHP"
    "y3rceda7gZV9RCL6J7MeJ2OrTNnQk71et0GdFB68rYNiuaBrSJeHzQBZzv7+Pnf99PS0HYtCsGzURbKQRCCcut7/x3S6gqVr"
    "HOzVmIUWIFHDi2DJpGwSTmOkyXwOweRmpxVQqEKPS0XAYZGTA5o+71fSv59NV42EhMXlhTTDfd1tQOPoGFDc2v70lmmJkQlI"
    "PDVGmjDxJ26DIhL9EaAYCuOx8lAOb1kmZyY6sh/repEpSKRVZdVg/Rqu5gZgsH6dxr2klqSNrCwwtB5/r4vLC3Zcz8YoGFnV"
    "ze+4I96hLMuDxnqfeNNsDBQPkm6rEvWONGheBHORJfFGwsenR0pu1yZOQpCp3cgxcXujTt+MiFxAAgB4OPpYcIePxqyvm6mn"
    "kXmUCJJroTm6U1C+Q+JZFG+nJjLhdu8+7DKPvVC8F+1a1co6VKpLyrHJm8o8qSVQraxbsQr8PpXqUlsj3h6cE4ksmdgFpSKV"
    "rNdtA8zbTsehbq5tdbQwmUGJ3O71yxl+4VhXy3qi691YVHeTA7zX0xrMbT6M4ZvCHJLDOioH1Yea3JiCyY0pfVlPtGmASgNe"
    "DYXXUbJZT3Q9W1LKeixY3cy3XfZ61gpOEgyvsOsXKYESzZ4q1SVhn4fqKFmJ6ihbmwyhLCAWJLwT5z1FZ0I2d2KiLFbE68Rv"
    "jevRhvDIgnTAMdHrWQfFsyIaJDyQXx42g7hUFH5TNGvWc7oBSrMilgWRcPrd9QLVXg4BEsHhPXOE7vPm+VPq8dW9A2F9lvXD"
    "KYzHLdpOMXfCKbNRoPoG0WM2tOIUPVu5unfQAYuE5Mu3q7gWJWs9KslAtpoXnacDFmn1vGt2gNIRe1RHMizrEZ3jJJijPu42"
    "BObMlXkOKWMLk0V4i8P6W8c51oK5bnXzLU0X3+zMlSuX1/oH/347hgmlPjkAAAAASUVORK5CYII="
)
