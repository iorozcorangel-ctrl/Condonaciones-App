"""
================================================================
  ASIGNACIÓN MASIVA DE NC (Gestión NC → Asignar NC)
  Lee un Excel de 3 columnas (A: Fecha NC, B: NC externo,
  C: Persona asignada — opcional) y reparte las NC en ciclo
  (round-robin) entre los usuarios marcados "En rotación".

  Regla del ciclo (confirmada con el usuario):
  - Las NC sin persona se reparten en orden 1, 2, 3 ... n, 1, 2 ...
  - Si una NC trae persona escrita a mano, se le asigna a esa persona
    y eso CUENTA COMO SU TURNO: la próxima vez que el ciclo llegue a
    ella, se la salta (se le guarda un "crédito").
  - El ciclo continúa donde se quedó la carga anterior (el estado
    se guarda en la tabla configuracion_app).
================================================================
"""
import unicodedata
from datetime import date, datetime, timedelta

import pandas as pd

from app.validaciones import validar_formato_nc, normalizar_numero_nc

CLAVE_ESTADO = "rotacion_nc"


# ── Utilidades ──────────────────────────────────────────────────
def _norm(texto) -> str:
    """Mayúsculas, sin acentos, sin espacios extra y sin '@' inicial."""
    if texto is None:
        return ""
    s = str(texto).strip()
    if s.lower() in ("nan", "none", "nat"):
        return ""
    s = s.lstrip("@")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.upper().split())


def parsear_fecha(valor):
    """Convierte lo que venga en la celda a date, o None si no se puede."""
    if valor is None:
        return None
    if isinstance(valor, pd.Timestamp):
        return None if pd.isna(valor) else valor.date()
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, (int, float)):
        if pd.isna(valor):
            return None
        if 20000 < float(valor) < 80000:          # número de serie de Excel
            return date(1899, 12, 30) + timedelta(days=int(valor))
        return None
    s = str(valor).strip()
    if not s or s.lower() in ("nan", "none", "nat"):
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%Y/%m/%d",
                "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def usuarios_en_rotacion(usuarios: list) -> list:
    """Usuarios activos marcados en rotación, ordenados por su número de orden
    (los que no tienen número van al final, por nombre)."""
    rot = [u for u in usuarios
           if u.get("activo") and u.get("en_rotacion", True) is not False]
    return sorted(rot, key=lambda u: (u.get("orden_rotacion") in (None, 0),
                                      u.get("orden_rotacion") or 0,
                                      _norm(u.get("nombre_completo"))))


# ── Lectura del Excel ───────────────────────────────────────────
def leer_excel_masivo(archivo):
    """
    Regresa (filas, error). Cada fila: {"fila", "fecha_raw", "nc_raw", "persona_raw"}.
    Usa las columnas A, B y C por posición (así lo definió el usuario).
    Si la primera fila es un encabezado (no trae fecha ni NC válidas), se omite.
    """
    try:
        df = pd.read_excel(archivo, header=None, dtype=object)
    except Exception as e:
        return [], f"No se pudo leer el Excel: {e}"
    if df.shape[1] < 2:
        return [], "El Excel debe tener al menos las columnas A (Fecha) y B (NC)."
    while df.shape[1] < 3:
        df[df.shape[1]] = None

    filas = []
    for i in range(len(df)):
        a, b, c = df.iat[i, 0], df.iat[i, 1], df.iat[i, 2]
        if all(_norm(x) == "" for x in (a, b, c)):
            continue                                    # fila vacía
        filas.append({"fila": i + 1, "fecha_raw": a, "nc_raw": b, "persona_raw": c})

    if filas:
        f0 = filas[0]
        es_encabezado = (parsear_fecha(f0["fecha_raw"]) is None and
                         not validar_formato_nc(normalizar_numero_nc(str(f0["nc_raw"] or ""))))
        if es_encabezado:
            filas = filas[1:]
    if not filas:
        return [], "El Excel no trae filas con datos."
    return filas, None


# ── Planeación del reparto ──────────────────────────────────────
def _buscar_usuario(texto, usuarios):
    t = _norm(texto)
    if not t:
        return None
    for u in usuarios:
        if t in (_norm(u.get("nombre_completo")), _norm(u.get("username"))):
            return u
    return None


def planear_asignacion(filas, usuarios, nc_existentes: set, estado: dict):
    """
    filas         → salida de leer_excel_masivo
    usuarios      → todos los usuarios (activos e inactivos)
    nc_existentes → set de NC ya creadas, normalizadas con _norm
    estado        → {"siguiente_id": ..., "creditos": {id: n}} de la carga anterior

    Regresa (plan, estado_nuevo, error_general).
    Cada elemento del plan: fila, fecha, nc, persona_id, persona_nombre,
    modo ("Ciclo"/"Manual"), ok (bool), motivo (texto).
    """
    rot = usuarios_en_rotacion(usuarios)
    ids_rot = [u["id"] for u in rot]
    creditos = {k: int(v) for k, v in (estado or {}).get("creditos", {}).items()
                if k in ids_rot and int(v) > 0}
    sig = (estado or {}).get("siguiente_id")
    ptr = ids_rot.index(sig) if sig in ids_rot else 0

    plan, vistos = [], set()
    for f in filas:
        item = {"fila": f["fila"], "fecha": None, "nc": "",
                "persona_id": None, "persona_nombre": "", "modo": "", "ok": False,
                "motivo": ""}
        fecha = parsear_fecha(f["fecha_raw"])
        nc = normalizar_numero_nc(str(f["nc_raw"])) if _norm(f["nc_raw"]) else ""
        item["nc"] = nc
        persona_txt = f["persona_raw"]

        if fecha is None:
            item["motivo"] = "Fecha inválida o vacía (columna A)"
        elif not nc:
            item["motivo"] = "Número de NC vacío (columna B)"
        elif not validar_formato_nc(nc):
            item["motivo"] = "Formato de NC inválido (debe ser NC- y 4 o 5 dígitos)"
        elif _norm(nc) in nc_existentes:
            item["motivo"] = "La NC ya existe en el sistema"
        elif _norm(nc) in vistos:
            item["motivo"] = "NC repetida dentro del mismo Excel"
        else:
            item["fecha"] = fecha
            if _norm(persona_txt):
                u = _buscar_usuario(persona_txt, usuarios)
                if u is None:
                    item["motivo"] = f"Persona no encontrada: «{persona_txt}»"
                elif not u.get("activo"):
                    item["motivo"] = f"La persona «{u['nombre_completo']}» está inactiva"
                else:
                    item.update(persona_id=u["id"], persona_nombre=u["nombre_completo"],
                                modo="Manual", ok=True, motivo="OK")
                    if u["id"] in ids_rot:          # cuenta como su turno
                        creditos[u["id"]] = creditos.get(u["id"], 0) + 1
            else:
                if not rot:
                    item["motivo"] = "No hay personas marcadas 'En rotación'"
                else:
                    while True:
                        uid = ids_rot[ptr]
                        ptr = (ptr + 1) % len(ids_rot)
                        if creditos.get(uid, 0) > 0:
                            creditos[uid] -= 1      # ya tuvo su turno con una manual
                            continue
                        break
                    u = rot[ids_rot.index(uid)]
                    item.update(persona_id=u["id"], persona_nombre=u["nombre_completo"],
                                modo="Ciclo", ok=True, motivo="OK")
        if item["ok"]:
            vistos.add(_norm(nc))
        plan.append(item)

    estado_nuevo = {
        "siguiente_id": ids_rot[ptr] if ids_rot else None,
        "creditos": {k: v for k, v in creditos.items() if v > 0},
    }
    return plan, estado_nuevo, None


def plantilla_excel_bytes() -> bytes:
    """Excel de ejemplo con las 3 columnas, para descargar."""
    import io
    df = pd.DataFrame({
        "Fecha NC": ["18/10/2026", "18/10/2026", "18/10/2026"],
        "NC Externo": ["NC-0001", "NC-0002", "NC-0003"],
        "Persona asignada (opcional)": ["", "", "Nombre Apellido"],
    })
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="NC")
        ws = w.sheets["NC"]
        for col, ancho in zip("ABC", (14, 16, 30)):
            ws.column_dimensions[col].width = ancho
    return buf.getvalue()
