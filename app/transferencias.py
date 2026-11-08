"""
================================================================
  MOTOR DEL MÓDULO "TRANSFERENCIAS"
  Lectura de los 2 archivos de entrada (por texto de encabezado,
  con alias), validaciones, cruce entre archivos y resolución de
  catálogos (Recinto / Naviera).
================================================================
"""

import pandas as pd

from app.validaciones import normalizar_contenedor, validar_formato_contenedor
from app.transferencias_config import (
    COL_RECINTO_ALIAS, COL_N4_ALIAS, CATEGORIA_TRANSBORDO, CATEGORIA_IMPORTACION,
    N4_CATEGORY_TRANSSHIP, N4_CATEGORY_IMPORT,
    OB_DCLRD_MODE_VESSEL, OB_DCLRD_MODE_TRUCK, T_STATE_INBOUND, T_STATE_YARD,
    TRUCKING_FIJO, ID_ESTADO_CONTENEDOR_FIJO, normalizar_texto, encontrar_columna,
    es_valor_verdadero,
)


# ════════════════════════════════════════════════════════════════
#   ARCHIVO RECINTO
# ════════════════════════════════════════════════════════════════

def procesar_archivo_recinto(df_raw):
    """
    Lee el Archivo Recinto, filtra por CATEGORIA (solo TRANSBORDO) y deja
    listas las columnas necesarias, ya normalizadas.

    Regresa (df_proc, alertas, error, contenedores_no_transbordo, df_sin_categoria):
      - df_proc: DataFrame con columnas CONTENEDOR, LINEA_NAVIERA,
        RECINTO_ORIGEN_NOMBRE, RECINTO_DESTINO_NOMBRE (o None si hubo error)
      - alertas: lista de strings (informativas)
      - error: string si falta una columna obligatoria, si no se pudo
        procesar nada; None si todo bien
      - contenedores_no_transbordo: set de contenedores (normalizados) que
        SÍ vienen en el Archivo Recinto como Importación y por eso se
        excluyeron del proceso a propósito — se usa más adelante para que
        el cruce contra el Archivo Sistema N4 no los marque como discrepancia.
      - df_sin_categoria: filas cuya CATEGORIA no es TRANSBORDO ni IMPORTACION
        (mal escrita o vacía, p. ej. "TRASNFERENCIAS"), con las mismas
        columnas que df_proc más CATEGORIA_ORIGINAL. No se descartan aquí:
        procesar_transferencias() decide con la columna Category del N4.
    """
    alertas = []
    cols = df_raw.columns

    col_categoria = encontrar_columna(cols, COL_RECINTO_ALIAS["categoria"])
    col_cont      = encontrar_columna(cols, COL_RECINTO_ALIAS["contenedor"])
    col_linea     = encontrar_columna(cols, COL_RECINTO_ALIAS["linea_naviera"])
    col_origen    = encontrar_columna(cols, COL_RECINTO_ALIAS["recinto_origen"])
    col_destino   = encontrar_columna(cols, COL_RECINTO_ALIAS["recinto_destino"])

    faltantes = []
    if not col_categoria: faltantes.append("CATEGORIA")
    if not col_cont:      faltantes.append("CONTENEDOR")
    if not col_origen:    faltantes.append("RECINTO ORIGEN")
    if not col_destino:   faltantes.append("RECINTO DESTINO")
    if faltantes:
        return None, alertas, (
            f"El Archivo Recinto no tiene la(s) columna(s): {', '.join(faltantes)}. "
            f"Favor de verificar los encabezados del archivo."
        ), set(), None

    df = df_raw.copy()
    df = df[df[col_cont].notna()].copy()

    # Se normaliza el contenedor ANTES de filtrar por categoría, para poder
    # identificar qué contenedores se excluyen (Importación u otra
    # categoría distinta de Transbordo) y así, más adelante, no marcarlos
    # como discrepancia si también aparecen en el Archivo Sistema N4.
    df["CONTENEDOR"] = df[col_cont].apply(normalizar_contenedor)
    df = df[df["CONTENEDOR"] != ""].copy()

    # ── Filtro por CATEGORIA ─────────────────────────────────────
    df["_categoria_norm"] = df[col_categoria].fillna("").apply(normalizar_texto)  # vacío ≠ "NAN"
    es_transbordo  = df["_categoria_norm"] == CATEGORIA_TRANSBORDO
    es_importacion = df["_categoria_norm"] == CATEGORIA_IMPORTACION
    es_sin_cat     = ~(es_transbordo | es_importacion)
    total_sin_cat  = int(es_sin_cat.sum())
    alertas.append(
        f"Total Transbordos: {int(es_transbordo.sum())} — "
        f"Total Importaciones (eliminadas): {int(es_importacion.sum())}"
        + (f" — Sin categoría válida: {total_sin_cat}" if total_sin_cat else "")
    )

    # Palabras no reconocidas en CATEGORIA (mal escritas o vacías): se avisa
    # cuáles y cuántas filas traen cada una, para saber cuál es el error.
    if total_sin_cat:
        conteo = df.loc[es_sin_cat, "_categoria_norm"].replace("", "(vacío)").value_counts()
        palabras = ", ".join(f"'{p}' ({n} fila{'s' if n != 1 else ''})" for p, n in conteo.items())
        alertas.append(
            f"La columna CATEGORIA del Archivo Recinto trae palabra(s) que el sistema no "
            f"reconoce (solo acepta TRANSBORDO o IMPORTACION): {palabras}. Para esos "
            f"contenedores se revisa la columna Category del Archivo Sistema N4: "
            f"Transship = se incluye como Transbordo, Import = se descarta. "
            f"Favor de corregir el archivo de origen."
        )

    contenedores_no_transbordo = set(df.loc[es_importacion, "CONTENEDOR"])

    df["LINEA_NAVIERA"]          = df[col_linea].apply(normalizar_texto) if col_linea else ""
    df["RECINTO_ORIGEN_NOMBRE"]  = df[col_origen]
    df["RECINTO_DESTINO_NOMBRE"] = df[col_destino]
    df["CATEGORIA_ORIGINAL"]     = df["_categoria_norm"]

    columnas = ["CONTENEDOR", "LINEA_NAVIERA", "RECINTO_ORIGEN_NOMBRE", "RECINTO_DESTINO_NOMBRE"]
    df_sin_categoria = df.loc[es_sin_cat, columnas + ["CATEGORIA_ORIGINAL"]].reset_index(drop=True)

    df = df[es_transbordo].copy()

    invalidos = [c for c in df["CONTENEDOR"] if not validar_formato_contenedor(c)]
    if invalidos:
        alertas.append(
            f"Contenedor(es) con formato inválido en el Archivo Recinto "
            f"(favor de corregir el archivo de origen): {', '.join(sorted(set(invalidos)))}"
        )

    df = df[columnas].reset_index(drop=True)

    return df, alertas, None, contenedores_no_transbordo, df_sin_categoria


# ════════════════════════════════════════════════════════════════
#   ARCHIVO SISTEMA N4
# ════════════════════════════════════════════════════════════════

def procesar_archivo_n4(df_raw):
    """
    Lee el Archivo Sistema N4 y deja listas las columnas necesarias.

    Regresa (df_proc, alertas, error):
      - df_proc: DataFrame con columnas UNIT_NBR, LINE_OP, TYPE_ARCH_ISO,
        T_STATE, OB_DCLRD_MODE, CATEGORY (o None si hubo error). CATEGORY es
        None en todas las filas si el archivo no trae la columna Category.
    """
    alertas = []
    cols = df_raw.columns

    col_ob    = encontrar_columna(cols, COL_N4_ALIAS["ob_dclrd_mode"])
    col_unit  = encontrar_columna(cols, COL_N4_ALIAS["unit_nbr"])
    col_tst   = encontrar_columna(cols, COL_N4_ALIAS["t_state"])
    col_line  = encontrar_columna(cols, COL_N4_ALIAS["line_op"])
    col_iso   = encontrar_columna(cols, COL_N4_ALIAS["type_arch_iso"])
    col_svsl  = encontrar_columna(cols, COL_N4_ALIAS["stop_vsl"])
    col_sroad = encontrar_columna(cols, COL_N4_ALIAS["stop_road"])
    col_cat   = encontrar_columna(cols, COL_N4_ALIAS["category"])

    faltantes = []
    if not col_unit: faltantes.append("Unit Nbr")
    if not col_line: faltantes.append("Line Op")
    if not col_iso:  faltantes.append("Type Arch ISO")
    if faltantes:
        return None, alertas, (
            f"El Archivo Sistema N4 no tiene la(s) columna(s): {', '.join(faltantes)}. "
            f"Favor de verificar los encabezados del archivo."
        )

    df = df_raw.copy()
    df = df[df[col_unit].notna()].copy()

    df["UNIT_NBR"] = df[col_unit].apply(normalizar_contenedor)
    df = df[df["UNIT_NBR"] != ""].copy()

    invalidos = [c for c in df["UNIT_NBR"] if not validar_formato_contenedor(c)]
    if invalidos:
        alertas.append(
            f"Contenedor(es) con formato inválido en el Archivo Sistema N4: "
            f"{', '.join(sorted(set(invalidos)))}"
        )

    df["LINE_OP"]       = df[col_line]
    df["LINE_OP_NORM"]  = df[col_line].apply(normalizar_texto)
    df["TYPE_ARCH_ISO"] = df[col_iso]
    df["T_STATE"]       = df[col_tst].apply(normalizar_texto) if col_tst else ""
    df["OB_DCLRD_MODE"] = df[col_ob].apply(normalizar_texto) if col_ob else ""
    df["STOP_VSL"]      = df[col_svsl].apply(es_valor_verdadero) if col_svsl else False
    df["STOP_ROAD"]     = df[col_sroad].apply(es_valor_verdadero) if col_sroad else False
    df["CATEGORY"]      = df[col_cat].apply(normalizar_texto) if col_cat else None

    # ── Consistencia T-State vs O/B Dclrd Mode (nunca bloquea) ───
    for _, row in df.iterrows():
        t_state = row["T_STATE"]
        ob_mode = row["OB_DCLRD_MODE"]
        if t_state == T_STATE_INBOUND and ob_mode == OB_DCLRD_MODE_TRUCK:
            alertas.append(
                f"Contenedor {row['UNIT_NBR']}: Inbound - Truck: un contenedor de "
                f"transferencia que no está ingresado a terminal no puede tener "
                f"modalidad de salida camión, favor revisar"
            )
        elif t_state == T_STATE_YARD and ob_mode == OB_DCLRD_MODE_VESSEL:
            alertas.append(
                f"Contenedor {row['UNIT_NBR']}: Yard - Vessel: un contenedor en "
                f"patio de transferencia no puede tener modalidad de salida buque, "
                f"favor revisar"
            )

    # ── Bloqueos Stop-Vsl / Stop-Road vs T-State (nunca bloquea) ─
    for _, row in df.iterrows():
        t_state = row["T_STATE"]
        if t_state == T_STATE_YARD and row["STOP_ROAD"]:
            alertas.append(
                f"Contenedor {row['UNIT_NBR']}: Se detectó que el contenedor en "
                f"patio tiene bloqueo modalidad de salida camión, favor validar"
            )
        if t_state == T_STATE_INBOUND and row["STOP_VSL"]:
            alertas.append(
                f"Contenedor {row['UNIT_NBR']}: Se detectó que el contenedor "
                f"pendiente de ingresar tiene bloqueo modalidad de salida buque, "
                f"favor validar"
            )

    df = df[["UNIT_NBR", "LINE_OP", "LINE_OP_NORM", "TYPE_ARCH_ISO", "T_STATE", "OB_DCLRD_MODE",
             "CATEGORY"]]
    df = df.reset_index(drop=True)

    return df, alertas, None


# ════════════════════════════════════════════════════════════════
#   CRUCE ENTRE AMBOS ARCHIVOS (ÚNICA VALIDACIÓN BLOQUEANTE)
# ════════════════════════════════════════════════════════════════

def validar_cruce(df_recinto, df_n4, contenedores_excluidos=None):
    """
    Compara CONTENEDOR (Archivo Recinto) contra UNIT_NBR (Archivo Sistema
    N4). Si no cuadran al 100%, regresa un error bloqueante — es la ÚNICA
    validación de este módulo que detiene el proceso.

    contenedores_excluidos: set de contenedores que SÍ vienen en el Archivo
    Recinto pero con categoría distinta de Transbordo (p. ej. Importación).
    Si uno de estos aparece en el Archivo Sistema N4, NO se marca como
    discrepancia — se excluyeron del proceso a propósito, no por un error
    real de captura.

    Regresa (ok, mensaje_error, totales)
    """
    contenedores_excluidos = contenedores_excluidos or set()

    set_recinto = set(df_recinto["CONTENEDOR"])
    set_n4      = set(df_n4["UNIT_NBR"])

    faltan_en_n4      = sorted(set_recinto - set_n4)
    faltan_en_recinto = sorted((set_n4 - set_recinto) - contenedores_excluidos)

    totales = {
        "total_recinto": len(set_recinto),
        "total_n4":      len(set_n4),
    }

    if not faltan_en_n4 and not faltan_en_recinto:
        return True, None, totales

    lineas = []
    for c in faltan_en_n4:
        lineas.append(f"No se encontró el contenedor {c} en el archivo Sistema N4, favor validar que cuadre la información")
    for c in faltan_en_recinto:
        lineas.append(f"No se encontró el contenedor {c} en el archivo Recinto, favor validar que cuadre la información")

    mensaje = (
        "\n".join(lineas) +
        f"\n\nTotal contenedores Archivo Recinto: {totales['total_recinto']} — "
        f"Total contenedores Archivo Sistema N4: {totales['total_n4']}"
    )
    return False, mensaje, totales


# ════════════════════════════════════════════════════════════════
#   RESOLUCIÓN DE CATÁLOGOS
# ════════════════════════════════════════════════════════════════

def resolver_recinto(nombre, catalogo_recintos, overrides=None):
    """
    catalogo_recintos: lista de dicts {codigo, nombre, ...} (de
    transferencias_recintos, incluye aprobados y pendientes — un nombre
    pendiente se usa igual, ver spec).
    overrides: dict {nombre_normalizado: codigo} elegido por el usuario en
    esta sesión para nombres que aún no existen en el catálogo.
    Regresa el código (int) o None si no se reconoce.
    """
    nombre_norm = normalizar_texto(nombre)
    if not nombre_norm:
        return None
    for r in catalogo_recintos:
        if normalizar_texto(r["nombre"]) == nombre_norm:
            return r["codigo"]
    if overrides and nombre_norm in overrides:
        return overrides[nombre_norm]
    return None


def resolver_naviera(nombre, catalogo_navieras):
    """catalogo_navieras: lista de dicts {codigo, nombre}."""
    nombre_norm = normalizar_texto(nombre)
    if not nombre_norm:
        return None
    for n in catalogo_navieras:
        if normalizar_texto(n["nombre"]) == nombre_norm:
            return n["codigo"]
    return None


# ════════════════════════════════════════════════════════════════
#   CATEGORIA MAL ESCRITA → DECIDE EL N4 (NUNCA BLOQUEA)
# ════════════════════════════════════════════════════════════════

def _decidir_categoria_con_n4(df_recinto, df_sin_cat, df_n4, contenedores_importacion):
    """
    Para las filas del Archivo Recinto cuya CATEGORIA no se reconoce
    (df_sin_cat), revisa la columna Category del Archivo Sistema N4:
      - Transship → se agrega a df_recinto como Transbordo.
      - Import    → se descarta.
      - Sin dato (no está en el N4, el N4 no trae la columna, u otro
        valor) → no se incluye.
    También avisa cuando el Archivo Recinto y el N4 no coinciden en la
    categoría; en ese caso manda lo que dice el Archivo Recinto.

    Regresa (df_recinto_actualizado, alertas, excluidos) — excluidos es el
    set de contenedores de df_sin_cat que NO se incluyeron, para que el
    cruce no los marque como discrepancia.
    """
    alertas = []
    cat_n4 = dict(zip(df_n4["UNIT_NBR"], df_n4["CATEGORY"]))
    n4_tiene_columna = df_n4["CATEGORY"].notna().any()

    # Avisos de categoría contradictoria (manda el Archivo Recinto)
    transbordo_vs_import = sorted(c for c in set(df_recinto["CONTENEDOR"])
                                  if cat_n4.get(c) == N4_CATEGORY_IMPORT)
    if transbordo_vs_import:
        alertas.append(
            f"Contenedor(es) que en el Archivo Recinto son TRANSBORDO pero en la columna "
            f"Category del Archivo Sistema N4 dicen Import (se respeta el Archivo Recinto "
            f"y SÍ se incluyen, favor validar): {', '.join(transbordo_vs_import)}"
        )
    importacion_vs_transship = sorted(c for c in contenedores_importacion
                                      if cat_n4.get(c) == N4_CATEGORY_TRANSSHIP)
    if importacion_vs_transship:
        alertas.append(
            f"Contenedor(es) que en el Archivo Recinto son IMPORTACION pero en la columna "
            f"Category del Archivo Sistema N4 dicen Transship (se respeta el Archivo "
            f"Recinto y NO se incluyen, favor validar): {', '.join(importacion_vs_transship)}"
        )

    if df_sin_cat is None or df_sin_cat.empty:
        return df_recinto, alertas, set()

    ya_transbordo = set(df_recinto["CONTENEDOR"])
    incluidos, descartados = [], []
    sin_decidir = {}   # motivo → [contenedores]
    for _, row in df_sin_cat.iterrows():
        cont = row["CONTENEDOR"]
        cat  = cat_n4.get(cont)
        if cont in ya_transbordo:
            continue   # también viene como TRANSBORDO en otra fila: ya está incluido
        if cont not in cat_n4:
            sin_decidir.setdefault("no aparece en el Archivo Sistema N4", []).append(cont)
        elif not n4_tiene_columna:
            sin_decidir.setdefault("el Archivo Sistema N4 no trae la columna Category", []).append(cont)
        elif cat == N4_CATEGORY_TRANSSHIP:
            incluidos.append(cont)
        elif cat == N4_CATEGORY_IMPORT:
            descartados.append(cont)
        else:
            motivo = f"Category del N4 = '{cat}'" if cat else "Category del N4 viene vacía"
            sin_decidir.setdefault(motivo, []).append(cont)

    if incluidos:
        alertas.append(
            f"Contenedor(es) con CATEGORIA mal escrita en el Archivo Recinto que SÍ se "
            f"incluyeron como Transbordo porque en el Archivo Sistema N4 dicen Transship "
            f"({len(set(incluidos))}): {', '.join(sorted(set(incluidos)))}"
        )
    if descartados:
        alertas.append(
            f"Contenedor(es) con CATEGORIA mal escrita en el Archivo Recinto que se "
            f"descartaron porque en el Archivo Sistema N4 dicen Import "
            f"({len(set(descartados))}): {', '.join(sorted(set(descartados)))}"
        )
    for motivo, conts in sin_decidir.items():
        alertas.append(
            f"Contenedor(es) con CATEGORIA mal escrita en el Archivo Recinto que NO se "
            f"incluyeron porque no se pudo decidir ({motivo}). Corrige la CATEGORIA en el "
            f"Archivo Recinto si deben ir: {', '.join(sorted(set(conts)))}"
        )

    df_incluir = df_sin_cat[df_sin_cat["CONTENEDOR"].isin(incluidos)][df_recinto.columns]
    df_recinto = pd.concat([df_recinto, df_incluir], ignore_index=True)
    excluidos = set(df_sin_cat["CONTENEDOR"]) - set(incluidos) - ya_transbordo
    return df_recinto, alertas, excluidos


# ════════════════════════════════════════════════════════════════
#   PROCESO COMPLETO
# ════════════════════════════════════════════════════════════════

def procesar_transferencias(df_recinto_raw, df_n4_raw, catalogo_recintos,
                             catalogo_navieras, overrides_recinto=None):
    """
    Orquesta todo el proceso. Regresa un dict:
      {
        "error_bloqueante": str o None,
        "alertas": [str, ...],
        "recintos_no_reconocidos": [nombre_original, ...] (únicos, sin duplicar),
        "filas": [ {contenedor, id_solicitante, linea_op_texto, type_arch_iso,
                     recinto_origen_codigo, recinto_destino_codigo}, ... ],
        "totales": {...},
      }
    Si "recintos_no_reconocidos" no está vacío, "filas" viene vacío — hace
    falta resolver esos nombres primero (el usuario los relaciona con un
    código existente) y volver a llamar a esta función con overrides_recinto.
    """
    alertas = []

    df_recinto, alertas_r, error_r, contenedores_no_transbordo, df_sin_cat = \
        procesar_archivo_recinto(df_recinto_raw)
    if error_r:
        return {"error_bloqueante": error_r, "alertas": [], "recintos_no_reconocidos": [],
                "filas": [], "totales": {}}
    alertas += alertas_r

    df_n4, alertas_n4, error_n4 = procesar_archivo_n4(df_n4_raw)
    if error_n4:
        return {"error_bloqueante": error_n4, "alertas": [], "recintos_no_reconocidos": [],
                "filas": [], "totales": {}}
    alertas += alertas_n4

    # ── CATEGORIA mal escrita o vacía: decide la columna Category del N4 ──
    # (nunca bloquea). Transship → se incluye como Transbordo; Import → se
    # descarta; si no se puede decidir, el contenedor no se incluye.
    df_recinto, alertas_cat, excluidos_por_categoria = _decidir_categoria_con_n4(
        df_recinto, df_sin_cat, df_n4, contenedores_no_transbordo)
    alertas += alertas_cat

    # ── Cruce (bloqueante) ───────────────────────────────────────
    # Los contenedores que en el Archivo Recinto son Importación (no
    # Transbordo) se excluyen del cruce: si también vienen en el Archivo
    # Sistema N4, no se consideran discrepancia, ya que a propósito no
    # forman parte de este proceso. Lo mismo con los de categoría mal
    # escrita que el N4 descartó o no pudo decidir (ya se avisó arriba).
    ok, error_cruce, totales = validar_cruce(
        df_recinto, df_n4, contenedores_no_transbordo | excluidos_por_categoria)
    if not ok:
        return {"error_bloqueante": error_cruce, "alertas": alertas,
                "recintos_no_reconocidos": [], "filas": [], "totales": totales}

    # Contenedores de Importación (no Transbordo) que SÍ aparecen en el N4:
    # se ignoran del cruce, solo aviso informativo (nunca bloquea).
    ignorados_en_n4 = sorted(set(df_n4["UNIT_NBR"]) & contenedores_no_transbordo)
    if ignorados_en_n4:
        alertas.append(
            f"Contenedor(es) ignorado(s) en el cruce porque en el Archivo Recinto son "
            f"Importación (no Transbordo), aunque sí aparecen en el Archivo Sistema N4: "
            f"{', '.join(ignorados_en_n4)}"
        )

    # Contenedores de Importación (no Transbordo) que NO aparecen en el N4:
    # tampoco se validan — solo se avisa, nunca es un error. Lo único que
    # nos interesa para el cruce son los contenedores de Transbordo.
    ignorados_fuera_n4 = sorted(contenedores_no_transbordo - set(df_n4["UNIT_NBR"]))
    if ignorados_fuera_n4:
        alertas.append(
            f"Contenedor(es) de Importación en el Archivo Recinto que no aparecen en el "
            f"Archivo Sistema N4 (no se consideran en el cruce): "
            f"{', '.join(ignorados_fuera_n4)}"
        )

    # ── Validación LINEA NAVIERA vs Line Op (nunca bloquea) ──────
    n4_por_cont = df_n4.set_index("UNIT_NBR")
    for _, row in df_recinto.iterrows():
        cont = row["CONTENEDOR"]
        if cont not in n4_por_cont.index:
            continue
        line_op_norm = n4_por_cont.loc[cont, "LINE_OP_NORM"]
        linea_naviera = row["LINEA_NAVIERA"]
        if linea_naviera and line_op_norm and linea_naviera != line_op_norm:
            alertas.append(
                f"Contenedor {cont}: la LINEA NAVIERA del Archivo Recinto "
                f"('{linea_naviera}') no coincide con Line Op del Archivo "
                f"Sistema N4 ('{line_op_norm}'), favor validar."
            )

    # ── Resolución de Recinto Origen/Destino ─────────────────────
    overrides_recinto = overrides_recinto or {}
    no_reconocidos = []
    filas = []

    for _, row in df_recinto.iterrows():
        cont = row["CONTENEDOR"]
        nom_origen  = row["RECINTO_ORIGEN_NOMBRE"]
        nom_destino = row["RECINTO_DESTINO_NOMBRE"]

        cod_origen  = resolver_recinto(nom_origen,  catalogo_recintos, overrides_recinto)
        cod_destino = resolver_recinto(nom_destino, catalogo_recintos, overrides_recinto)

        if cod_origen is None and nom_origen:
            no_reconocidos.append(str(nom_origen))
        if cod_destino is None and nom_destino:
            no_reconocidos.append(str(nom_destino))

        if cont in n4_por_cont.index:
            n4_row = n4_por_cont.loc[cont]
            line_op_texto = n4_row["LINE_OP"]
            type_arch_iso = n4_row["TYPE_ARCH_ISO"]
            cod_naviera   = resolver_naviera(line_op_texto, catalogo_navieras)
        else:
            line_op_texto = ""
            type_arch_iso = ""
            cod_naviera   = None

        filas.append({
            "contenedor":            cont,
            "id_solicitante":        cod_naviera,
            "linea_op_texto":        line_op_texto,
            "type_arch_iso":         type_arch_iso,
            "recinto_origen_nombre":  nom_origen,
            "recinto_destino_nombre": nom_destino,
            "recinto_origen_codigo":  cod_origen,
            "recinto_destino_codigo": cod_destino,
        })

    no_reconocidos = sorted(set(no_reconocidos))

    if no_reconocidos:
        return {"error_bloqueante": None, "alertas": alertas,
                "recintos_no_reconocidos": no_reconocidos, "filas": [], "totales": totales}

    # ── Navieras no reconocidas (informativo, no detiene: se genera
    #    con "Id Solicitante" vacío para que se revise manualmente) ──
    navieras_no_reconocidas = sorted({
        f["linea_op_texto"] for f in filas
        if f["id_solicitante"] is None and f["linea_op_texto"]
    })
    if navieras_no_reconocidas:
        alertas.append(
            f"Naviera(s) no reconocida(s) en el catálogo (favor de agregarlas desde "
            f"Usuarios): {', '.join(navieras_no_reconocidas)}"
        )

    return {"error_bloqueante": None, "alertas": alertas, "recintos_no_reconocidos": [],
            "filas": filas, "totales": totales}
