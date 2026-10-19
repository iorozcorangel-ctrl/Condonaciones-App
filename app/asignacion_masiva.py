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


def plantilla_excel_bytes(usuarios: list = None) -> bytes:
    """
    Machote descargable para la asignación masiva:
      Hoja 1 "Cargar NC"     → encabezados listos para llenar (la que se sube).
                               Columna C con lista desplegable de personas activas.
      Hoja 2 "Instrucciones" → cómo llenarlo, reglas del ciclo y ejemplos.
      Hoja 3 "Personas"      → nombres válidos para la columna C.
    El sistema solo lee la PRIMERA hoja, así que las otras no estorban al subirlo.
    """
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.worksheet.datavalidation import DataValidation

    naranja = PatternFill("solid", fgColor="E65100")
    crema   = PatternFill("solid", fgColor="FFF3E0")
    blanco_b = Font(bold=True, color="FFFFFF")
    negrita  = Font(bold=True)
    borde    = Border(*(Side(style="thin", color="BDBDBD"),) * 4)
    centro   = Alignment(horizontal="center", vertical="center", wrap_text=True)

    activos = [u for u in (usuarios or []) if u.get("activo")]
    activos = sorted(activos, key=lambda u: _norm(u.get("nombre_completo")))

    wb = Workbook()

    # ── Hoja 1: Cargar NC ───────────────────────────────────────
    ws = wb.active
    ws.title = "Cargar NC"
    encabezados = ["Fecha NC (dd/mm/aaaa)", "NC Externo (NC-####)", "Persona asignada (opcional)"]
    for col, (txt, ancho) in enumerate(zip(encabezados, (22, 22, 34)), start=1):
        c = ws.cell(row=1, column=col, value=txt)
        c.fill, c.font, c.alignment, c.border = naranja, blanco_b, centro, borde
        ws.column_dimensions["ABC"[col - 1]].width = ancho
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"
    for fila in range(2, 1002):
        ws.cell(row=fila, column=1).number_format = "DD/MM/YYYY"
        ws.cell(row=fila, column=2).number_format = "@"

    # ── Hoja 3: Personas (se crea antes para la lista desplegable) ──
    wp = wb.create_sheet("Personas")
    wp["A1"], wp["B1"], wp["C1"] = "Nombre completo", "Usuario", "¿En rotación?"
    for c in (wp["A1"], wp["B1"], wp["C1"]):
        c.fill, c.font, c.alignment = naranja, blanco_b, centro
    for i, u in enumerate(activos, start=2):
        wp.cell(row=i, column=1, value=u.get("nombre_completo"))
        wp.cell(row=i, column=2, value=u.get("username"))
        wp.cell(row=i, column=3,
                value="Sí" if u.get("en_rotacion", True) is not False else "No (vacaciones / fuera del ciclo)")
    wp.column_dimensions["A"].width = 30
    wp.column_dimensions["B"].width = 18
    wp.column_dimensions["C"].width = 34
    if activos:
        dv = DataValidation(type="list", formula1=f"=Personas!$A$2:$A${len(activos) + 1}",
                            allow_blank=True, showErrorMessage=False)
        dv.promptTitle = "Persona asignada (opcional)"
        dv.prompt = "Déjalo vacío para que el sistema asigne en ciclo, o elige a alguien de la lista."
        dv.showInputMessage = True
        ws.add_data_validation(dv)
        dv.add("C2:C1001")

    # ── Hoja 2: Instrucciones ───────────────────────────────────
    wi = wb.create_sheet("Instrucciones", 1)
    wi.column_dimensions["A"].width = 26
    wi.column_dimensions["B"].width = 95
    lineas = [
        ("titulo", "Machote — Asignación masiva de NC", ""),
        ("", "", ""),
        ("seccion", "Cómo llenarlo", ""),
        ("", "1. Llena la hoja «Cargar NC»", "Una NC por fila, empezando en la fila 2. No cambies el orden de las columnas."),
        ("", "2. Columna A — Fecha NC", "Obligatoria. Fecha de solicitud de la NC, formato dd/mm/aaaa (ej. 18/10/2026)."),
        ("", "3. Columna B — NC Externo", "Obligatoria. Formato NC- y 4 o 5 dígitos (ej. NC-2585, NC-10000). "
                                          "Se aceptan minúsculas y espacios sobrantes; «2585» o «NC2585» se rechazan."),
        ("", "4. Columna C — Persona", "Opcional. VACÍA = el sistema la asigna en ciclo. Con nombre = se asigna a esa "
                                       "persona (usa la lista desplegable o la hoja «Personas»; también acepta el usuario)."),
        ("", "5. Súbelo", "Gestión NC → Asignar NC → «📥 Asignación masiva desde Excel» → Previsualizar → Confirmar."),
        ("", "", ""),
        ("seccion", "Cómo funciona el ciclo", ""),
        ("", "Reparto", "Las NC sin persona se reparten 1, 2, 3 … y vuelve a empezar, solo entre quienes "
                        "están «En rotación» (se configura en 👥 Usuarios)."),
        ("", "Asignación manual", "Si una NC trae persona, cuenta como su turno: el ciclo se la salta la próxima vez."),
        ("", "Continuidad", "El ciclo sigue donde se quedó la carga anterior."),
        ("", "", ""),
        ("seccion", "Se rechaza la fila si…", ""),
        ("", "", "• Fecha vacía o inválida  • NC vacía o con formato incorrecto  • La NC ya existe en el sistema"),
        ("", "", "• La NC se repite dentro del mismo Excel  • La persona no existe o está inactiva"),
        ("", "", "Las filas con error se omiten y las demás se crean; antes de crear verás una previsualización."),
        ("", "", ""),
        ("seccion", "Ejemplo (NO lo copies a la hoja «Cargar NC»)", ""),
        ("ejemplo_h", "Fecha NC | NC Externo | Persona", "Resultado"),
        ("ejemplo", "18/10/2026 | NC-0001 | (vacío)", "Se asigna a quien siga en el ciclo"),
        ("ejemplo", "18/10/2026 | NC-0002 | Saul Vasquez", "Se asigna a Saul y el ciclo lo salta la próxima vez"),
        ("ejemplo", "18/10/2026 | 0003 | (vacío)", "❌ Rechazada: formato de NC inválido"),
    ]
    for r, (tipo, a, b) in enumerate(lineas, start=1):
        ca, cb = wi.cell(row=r, column=1, value=a), wi.cell(row=r, column=2, value=b)
        cb.alignment = Alignment(wrap_text=True, vertical="top")
        ca.alignment = Alignment(wrap_text=True, vertical="top")
        if tipo == "titulo":
            ca.font = Font(bold=True, size=14, color="E65100")
        elif tipo == "seccion":
            ca.font = blanco_b
            ca.fill = cb.fill = naranja
        elif tipo == "ejemplo_h":
            ca.font = cb.font = negrita
            ca.fill = cb.fill = crema
        elif a:
            ca.font = negrita

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
