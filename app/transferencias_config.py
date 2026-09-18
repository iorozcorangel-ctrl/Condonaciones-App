"""
================================================================
  CONFIGURACIÓN DEL MÓDULO "TRANSFERENCIAS"
  Mapeo de columnas (con alias, por texto de encabezado —
  nunca por posición), catálogos iniciales y constantes fijas
  del documento final.
================================================================
"""

import unicodedata


# ── Constantes fijas del documento final ────────────────────────
TRUCKING_FIJO             = "TC-TAE121220E95-01"
ID_ESTADO_CONTENEDOR_FIJO = 1

# Orden de las 8 columnas del documento final (empiezan en columna B,
# la columna A siempre queda vacía y más angosta)
COLUMNAS_DOC_FINAL = [
    "Id Solicitante",
    "No Contenedor",
    "Linea Op",
    "Type Arch ISO",
    "Recinto Origen",
    "Recinto Destino",
    "Id Estado Contenedor",
    "Trucking",
]


# ── Normalización de texto (para encabezados y valores) ─────────
def normalizar_texto(valor):
    """Mayúsculas, sin espacios extra (incluyendo al final), sin acentos."""
    if valor is None:
        return ""
    s = str(valor).strip().upper()
    s = " ".join(s.split())  # colapsa espacios múltiples
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


def encontrar_columna(columnas_df, alias_lista):
    """
    Busca en las columnas reales de un DataFrame (columnas_df) alguna que
    coincida (normalizada) con alguno de los alias esperados. Regresa el
    nombre REAL de la columna tal como viene en el archivo, o None si no
    se encontró ninguna coincidencia.
    """
    normalizadas = {normalizar_texto(c): c for c in columnas_df}
    for alias in alias_lista:
        real = normalizadas.get(normalizar_texto(alias))
        if real is not None:
            return real
    return None


# ── Archivo Recinto (llenado a mano, alta variabilidad) ──────────
# Cada campo tiene una lista de alias reconocidos para el encabezado.
COL_RECINTO_ALIAS = {
    "categoria":       ["CATEGORIA", "CATEGORÍA"],
    "numero":          ["#", "NO", "NO.", "NUM", "NÚM"],
    "contenedor":      ["CONTENEDOR", "NO CONTENEDOR", "NO. CONTENEDOR",
                         "CONTENEDOR NO", "CONTENEDOR NO.",
                         "NUMERO DE CONTENEDOR", "NÚMERO DE CONTENEDOR"],
    "linea_naviera":   ["LINEA NAVIERA", "LÍNEA NAVIERA", "NAVIERA"],
    "sellos1":         ["SELLOS1", "SELLO1", "SELLOS 1", "SELLO 1"],
    "sellos2":         ["SELLOS2", "SELLO2", "SELLOS 2", "SELLO 2"],
    "sellos3":         ["SELLOS3", "SELLO3", "SELLOS 3", "SELLO 3"],
    "sellos4":         ["SELLOS4", "SELLO4", "SELLOS 4", "SELLO 4"],
    "importador":      ["IMPORTADOR // CONSIGNATARIO", "IMPORTADOR/CONSIGNATARIO",
                         "IMPORTADOR", "CONSIGNATARIO"],
    "mercancia":       ["MERCANCIA", "MERCANCÍA"],
    "reefer":          ["REEFER"],
    "recinto_origen":  ["RECINTO ORIGEN", "RECINTO DE ORIGEN"],
    "recinto_destino": ["RECINTO DESTINO", "RECINTO DE DESTINO"],
    "status":          ["STATUS 112-902/111", "STATUS 112-902-111", "STATUS"],
    "fecha_horario":   ["FECHA/HORARIO", "FECHA HORARIO"],
}

# Valores válidos del campo CATEGORIA (normalizados)
CATEGORIA_TRANSBORDO   = "TRANSBORDO"
CATEGORIA_IMPORTACION  = "IMPORTACION"


# ── Archivo Sistema N4 (viene de sistema, poca variabilidad) ─────
COL_N4_ALIAS = {
    "ob_dclrd_mode": ["O/B Dclrd Mode", "OB Dclrd Mode", "O/B Declared Mode"],
    "unit_nbr":      ["Unit Nbr", "Unit Number", "UnitNbr"],
    "t_state":       ["T-State", "TState", "T State"],
    "line_op":       ["Line Op", "LineOp"],
    "type_arch_iso": ["Type Arch ISO", "TypeArchISO", "Type Arch"],
}

# Valores válidos (normalizados)
OB_DCLRD_MODE_VESSEL = "VESSEL"
OB_DCLRD_MODE_TRUCK  = "TRUCK"
T_STATE_INBOUND      = "INBOUND"
T_STATE_YARD         = "YARD"


# ── Catálogo inicial — Recinto Origen/Destino (código fijo, no editable) ──
# (nombre tal como puede venir escrito, código correspondiente)
RECINTOS_INICIALES = [
    ("API",              85),
    ("LA JUNTA",         6383),
    ("OCUPA",            4747),
    ("SSA",              6381),
    ("SSA MEXICO",       6381),
    ("SSA MÉXICO",       6381),
    ("SSAMEXICO",        6381),
    ("SSAMÉXICO",        6381),
    ("TIMSA",            6382),
    ("CEMEX",            160),
    ("CORPORACION",      154),
    ("CONTECON",         480),
    ("FRIMAN",           6),
    ("HAZESA",           2164),
]

# ── Catálogo inicial — Naviera → Código (para "Id Solicitante") ─
NAVIERAS_INICIALES = [
    ("ONE", 4629),
    ("CMA",  3472),
    ("MSC",  4),
    ("HLC",  6375),
    ("EVG",  5080),
    ("WHL",  5020),
    ("COS",  6384),
    ("OOL",  3472),
]
