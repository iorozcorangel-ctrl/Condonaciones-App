"""
================================================================
  MOTOR DE VALIDACIONES Y REGLAS DE NEGOCIO
  Aplica las 9 reglas y genera resultados por contenedor
================================================================
"""

import pandas as pd
from datetime import date, datetime as dt_datetime, timedelta
from app.config import COL_BI, COL_TAB
from app.calendario import (calcular_desfase_regla3, calcular_desfase_regla4,
                             calcular_desfase_regla5)


def normalizar_contenedor(valor):
    if pd.isna(valor):
        return ""
    s = str(valor).strip().upper().replace(" ", "")
    return s


def validar_formato_contenedor(contenedor):
    if len(contenedor) != 11:
        return False
    if not contenedor[:4].isalpha():
        return False
    if not contenedor[4:].isdigit():
        return False
    return True


def to_date(valor):
    """
    Convierte cualquier tipo de fecha a datetime.date puro.
    Maneja: datetime.datetime, datetime.date, pandas Timestamp, strings.
    """
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except Exception:
        pass
    if valor == "":
        return None
    # datetime.datetime primero (es subclase de date, debe ir antes)
    if isinstance(valor, dt_datetime):
        return valor.date()
    # date puro
    if isinstance(valor, date):
        return valor
    # pandas Timestamp u objetos con .date()
    if hasattr(valor, "date") and callable(getattr(valor, "date")):
        try:
            return valor.date()
        except Exception:
            pass
    # Conversión desde string
    try:
        return pd.to_datetime(valor).date()
    except Exception:
        return None


def to_int(valor, default=0):
    try:
        if pd.isna(valor):
            return default
        return int(valor)
    except Exception:
        return default


def to_float(valor, default=0.0):
    try:
        if pd.isna(valor):
            return default
        return float(valor)
    except Exception:
        return default


def validar_archivos(df_tab, df_bi):
    errores      = []
    advertencias = []

    col_tab = COL_TAB["contenedor"]
    col_bi  = COL_BI["contenedor"]

    if col_tab not in df_tab.columns:
        errores.append(f"El Tabulador Comercial no tiene la columna '{col_tab}'")
        return None, None, errores, advertencias

    if col_bi not in df_bi.columns:
        errores.append(f"El Archivo BI no tiene la columna '{col_bi}'")
        return None, None, errores, advertencias

    df_tab = df_tab.copy()
    df_bi  = df_bi.copy()
    df_tab[col_tab] = df_tab[col_tab].apply(normalizar_contenedor)
    df_bi[col_bi]   = df_bi[col_bi].apply(normalizar_contenedor)

    for cont in df_tab[col_tab]:
        if cont and not validar_formato_contenedor(cont):
            errores.append(f"El contenedor no viene en formato correcto: '{cont}' (Tabulador Comercial)")
    for cont in df_bi[col_bi]:
        if cont and not validar_formato_contenedor(cont):
            errores.append(f"El contenedor no viene en formato correcto: '{cont}' (Archivo BI)")

    if errores:
        return None, None, errores, advertencias

    dups_tab = df_tab[df_tab[col_tab].duplicated(keep=False)][col_tab].unique()
    dups_bi  = df_bi[df_bi[col_bi].duplicated(keep=False)][col_bi].unique()

    for d in dups_tab:
        if d:
            advertencias.append(f"Contenedor duplicado en Tabulador Comercial: {d}")
    for d in dups_bi:
        if d:
            advertencias.append(f"Contenedor duplicado en Archivo BI: {d}")

    set_tab = set(df_tab[col_tab].tolist())
    set_bi  = set(df_bi[col_bi].tolist())

    solo_tab = set_tab - set_bi
    solo_bi  = set_bi - set_tab

    for c in solo_tab:
        if c:
            errores.append(f"Un Contenedor no viene mencionado en uno de los archivos: '{c}' — No encontrado en Archivo BI")
    for c in solo_bi:
        if c:
            errores.append(f"Un Contenedor no viene mencionado en uno de los archivos: '{c}' — No encontrado en Tabulador Comercial")

    if errores:
        return None, None, errores, advertencias

    df_tab = df_tab.sort_values(col_tab).reset_index(drop=True)
    df_bi  = df_bi.sort_values(col_bi).reset_index(drop=True)

    return df_tab, df_bi, errores, advertencias


def aplicar_regla1(df_bi, df_tab, fecha_solicitud_global, fechas_por_contenedor, perfil):
    if not perfil.get("regla1_activa", True):
        return []

    no_cumplen = []
    for _, row in df_bi.iterrows():
        cont     = row[COL_BI["contenedor"]]
        time_out = to_date(row.get(COL_BI["time_out"]))
        if not time_out:
            continue
        fecha_sol = fechas_por_contenedor.get(cont, fecha_solicitud_global)
        if not fecha_sol:
            continue
        diff = (fecha_sol - time_out).days
        if diff > 30:
            no_cumplen.append(cont)
    return no_cumplen


def aplicar_regla2(df_bi, perfil):
    if not perfil.get("regla2_activa", True):
        return []

    no_cumplen = []
    for _, row in df_bi.iterrows():
        cont    = row[COL_BI["contenedor"]]
        time_in = to_date(row.get(COL_BI["time_in"]))
        if not time_in:
            continue

        fecha_limite = time_in + timedelta(days=3)

        fecha_previo = to_date(row.get(COL_BI["fecha_previo"]))
        fecha_lib    = to_date(row.get(COL_BI["fecha_liberacion"]))

        cumple = False
        if fecha_previo and fecha_previo <= fecha_limite:
            cumple = True
        if fecha_lib and fecha_lib <= fecha_limite:
            cumple = True

        if not cumple:
            no_cumplen.append(cont)
    return no_cumplen


def calcular_desfases(df_bi, dias_especiales, perfil):
    resultados = {}
    dias_previo    = perfil.get("dias_previo",    3)
    dias_ferromex  = perfil.get("dias_ferromex",  3)
    dias_carretero = perfil.get("dias_carretero", 2)

    for _, row in df_bi.iterrows():
        cont = row[COL_BI["contenedor"]]

        # Regla 3
        fecha_previo   = to_date(row.get(COL_BI["fecha_previo"]))
        fecha_posicion = to_date(row.get(COL_BI["fecha_posicion"]))

        if not fecha_previo:
            desfase_previo = 0
        elif not fecha_posicion:
            desfase_previo = 0
        else:
            desfase_previo, _ = calcular_desfase_regla3(
                fecha_previo, fecha_posicion, dias_especiales, dias_previo
            )

        # Regla 4
        fecha_ferromex = to_date(row.get(COL_BI["fecha_ferromex"]))
        fecha_gondola  = to_date(row.get(COL_BI["fecha_gondola"]))

        if not fecha_ferromex or not fecha_gondola:
            desfase_ffcc = 0
        else:
            desfase_ffcc, _ = calcular_desfase_regla4(
                fecha_ferromex, fecha_gondola, dias_ferromex
            )

        # Regla 5
        fecha_entrega = to_date(row.get(COL_BI["fecha_entrega"]))
        fecha_timeout = to_date(row.get(COL_BI["time_out"]))

        if not fecha_entrega or not fecha_timeout:
            desfase_carretero = 0
        else:
            desfase_carretero, _ = calcular_desfase_regla5(
                fecha_entrega, fecha_timeout, dias_especiales, dias_carretero
            )

        total = desfase_previo + desfase_ffcc + desfase_carretero

        resultados[cont] = {
            "desfase_previo":    desfase_previo,
            "desfase_ffcc":      desfase_ffcc,
            "desfase_carretero": desfase_carretero,
            "total_desfase":     total,
        }

    return resultados


def calcular_montos(df_bi, desfases):
    resultados = {}

    for _, row in df_bi.iterrows():
        cont = row[COL_BI["contenedor"]]
        d    = desfases.get(cont, {})
        total_desfase = d.get("total_desfase", 0)

        # Regla 7
        alm_qty      = to_float(row.get(COL_BI["alm_qty"]), 0)
        alm_subtotal = to_float(row.get(COL_BI["alm_subtotal"]), 0)

        if alm_qty <= 0:
            dias_alm_condonar = 0
            dias_alm_cobrar   = 0
            monto_alm         = 0.0
        else:
            costo_dia_alm     = alm_subtotal / alm_qty
            dias_desfase_alm  = min(total_desfase, alm_qty)
            dias_alm_condonar = dias_desfase_alm
            dias_alm_cobrar   = max(alm_qty - dias_desfase_alm, 0)
            monto_alm         = costo_dia_alm * dias_alm_condonar

        # Regla 8
        energia_qty      = to_float(row.get(COL_BI["energia_qty"]), 0)
        energia_subtotal = to_float(row.get(COL_BI["energia_subtotal"]), 0)

        if energia_qty <= 0:
            dias_conex_condonar = 0
            dias_conex_cobrar   = 0
            monto_conex         = 0.0
        else:
            costo_dia_conex     = energia_subtotal / energia_qty
            dias_desfase_conex  = min(total_desfase, energia_qty)
            dias_conex_condonar = dias_desfase_conex
            dias_conex_cobrar   = max(energia_qty - dias_desfase_conex, 0)
            monto_conex         = costo_dia_conex * dias_conex_condonar

        # Regla 9
        admon_qty      = to_float(row.get(COL_BI["admon_qty"]), 0)
        admon_subtotal = to_float(row.get(COL_BI["admon_subtotal"]), 0)

        admon_cobrado = admon_qty > 0
        aplica_admon  = admon_cobrado and (total_desfase >= alm_qty) and alm_qty > 0
        monto_admon   = admon_subtotal if aplica_admon else 0.0

        # No Show
        no_show_qty      = to_float(row.get(COL_BI["no_show_qty"]), 0)
        no_show_subtotal = to_float(row.get(COL_BI["no_show_subtotal"]), 0)

        monto_total = monto_alm + monto_conex + monto_admon

        resultados[cont] = {
            "alm_qty":            alm_qty,
            "dias_alm_condonar":  dias_alm_condonar,
            "dias_alm_cobrar":    dias_alm_cobrar,
            "monto_alm":          round(monto_alm, 2),
            "energia_qty":        energia_qty,
            "dias_conex_condonar":dias_conex_condonar,
            "dias_conex_cobrar":  dias_conex_cobrar,
            "monto_conex":        round(monto_conex, 2),
            "admon_cobrado":      "SI" if admon_cobrado else "NO",
            "aplica_admon":       "SI" if aplica_admon else "NO",
            "monto_admon":        round(monto_admon, 2),
            "no_show_qty":        int(no_show_qty),
            "no_show_subtotal":   round(no_show_subtotal, 2),
            "monto_total":        round(monto_total, 2),
        }

    return resultados


def generar_comentario(cont, desfases, montos):
    d = desfases.get(cont, {})
    partes = []

    dp = d.get("desfase_previo", 0)
    df = d.get("desfase_ffcc", 0)
    dc = d.get("desfase_carretero", 0)

    if dp > 0:
        partes.append(
            f"Se generaron {dp} día(s) de almacenaje no procedente(s) al cliente "
            f"por desfase en previo, siendo procedente la condonación de {dp} día(s)"
        )
    if df > 0:
        partes.append(
            f"Se detectaron {df} día(s) de desfase en carga a góndola ferroviaria, "
            f"siendo procedente la condonación de {df} día(s)"
        )
    if dc > 0:
        partes.append(
            f"Se detectaron {dc} día(s) de desfase en entrega carretero, "
            f"siendo procedente la condonación de {dc} día(s)"
        )

    if not partes:
        return "No se detectaron días de desfase procedentes para condonación"

    return " | ".join(partes)
