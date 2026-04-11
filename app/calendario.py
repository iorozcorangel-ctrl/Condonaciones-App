"""
================================================================
  MÓDULO DE CALENDARIO Y DÍAS NO HÁBILES
  Gestiona festivos oficiales y días especiales marcados
================================================================
"""

import json, os
from datetime import date, timedelta
from app.config import FESTIVOS_FIJOS, FESTIVOS_VARIABLES

ARCHIVO_FESTIVOS = os.path.join(os.path.dirname(__file__), "..", "festivos_especiales.json")


def get_festivos_oficiales(anio):
    festivos = set()
    for mes, dia in FESTIVOS_FIJOS:
        try:
            festivos.add(date(anio, mes, dia))
        except ValueError:
            pass
    for f in FESTIVOS_VARIABLES.get(anio, []):
        try:
            festivos.add(date(anio, f[0], f[1]))
        except ValueError:
            pass
    return festivos


def es_festivo_oficial(fecha):
    return fecha in get_festivos_oficiales(fecha.year)


def cargar_dias_especiales():
    try:
        if os.path.exists(ARCHIVO_FESTIVOS):
            with open(ARCHIVO_FESTIVOS, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {date.fromisoformat(d) for d in data}
    except Exception:
        pass
    return set()


def guardar_dias_especiales(dias):
    try:
        with open(ARCHIVO_FESTIVOS, "w", encoding="utf-8") as f:
            json.dump([d.isoformat() for d in dias], f)
    except Exception:
        pass


def limpiar_dias_especiales():
    guardar_dias_especiales(set())
    return set()


def es_dia_no_habil_regla3(fecha, dias_especiales):
    """Regla 3 — No hábil: domingo, festivo oficial, día especial marcado"""
    if fecha.weekday() == 6:
        return True
    if es_festivo_oficial(fecha):
        return True
    if fecha in dias_especiales:
        return True
    return False


def es_dia_no_habil_regla5(fecha, dias_especiales, programo_jueves_viernes=False):
    """Regla 5 — No hábil: domingo siempre, sábado si programó Jue/Vie, festivos, especiales"""
    if fecha.weekday() == 6:
        return True
    if programo_jueves_viernes and fecha.weekday() == 5:
        return True
    if es_festivo_oficial(fecha):
        return True
    if fecha in dias_especiales:
        return True
    return False


def calcular_dias_habiles_hacia_adelante(fecha_inicio, n_dias, dias_especiales,
                                          regla="3", programo_jueves_viernes=False):
    """
    Calcula la fecha límite sumando n_dias hábiles desde fecha_inicio.
    El día de inicio NO cuenta, se empieza a contar desde el día siguiente.
    """
    fecha_actual = fecha_inicio + timedelta(days=1)
    dias_contados = 0
    while dias_contados < n_dias:
        if regla == "3":
            if not es_dia_no_habil_regla3(fecha_actual, dias_especiales):
                dias_contados += 1
        elif regla == "5":
            if not es_dia_no_habil_regla5(fecha_actual, dias_especiales, programo_jueves_viernes):
                dias_contados += 1
        if dias_contados < n_dias:
            fecha_actual += timedelta(days=1)
    return fecha_actual


def calcular_desfase_regla3(fecha_solicitud, fecha_posicion, dias_especiales,
                              dias_plazo=3):
    """
    Regla 3 — Calcula días de desfase en previo.
    Retorna (dias_desfase, fecha_limite)
    """
    if not fecha_solicitud or not fecha_posicion:
        return 0, None

    fecha_limite = calcular_dias_habiles_hacia_adelante(
        fecha_solicitud, dias_plazo, dias_especiales, regla="3"
    )

    if fecha_posicion <= fecha_limite:
        return 0, fecha_limite

    # Contar días de desfase desde el día siguiente al límite hasta posicionamiento
    # Los días del calendario ya NO se saltan si hay desfase
    dias_desfase = 0
    fecha_actual = fecha_limite + timedelta(days=1)
    while fecha_actual <= fecha_posicion:
        dias_desfase += 1
        fecha_actual += timedelta(days=1)

    return dias_desfase, fecha_limite


def calcular_desfase_regla4(fecha_ferromex, fecha_gondola, dias_plazo=3):
    """
    Regla 4 — Calcula días de desfase en carga a góndola FFCC.
    Conteo en días naturales, sin excepciones.
    """
    if not fecha_ferromex or not fecha_gondola:
        return 0, None

    fecha_limite = fecha_ferromex + timedelta(days=dias_plazo)

    if fecha_gondola <= fecha_limite:
        return 0, fecha_limite

    dias_desfase = 0
    fecha_actual = fecha_limite + timedelta(days=1)
    while fecha_actual <= fecha_gondola:
        dias_desfase += 1
        fecha_actual += timedelta(days=1)

    return dias_desfase, fecha_limite


def calcular_desfase_regla5(fecha_programacion, fecha_timeout, dias_especiales,
                              dias_plazo=2):
    """
    Regla 5 — Calcula días de desfase en entrega carretero.
    Sábado no cuenta en plazo si programó Jue o Vie.
    """
    if not fecha_programacion or not fecha_timeout:
        return 0, None

    dia_semana = fecha_programacion.weekday()  # 3=Jue, 4=Vie
    prog_jue_vie = dia_semana in (3, 4)

    fecha_limite = calcular_dias_habiles_hacia_adelante(
        fecha_programacion, dias_plazo, dias_especiales,
        regla="5", programo_jueves_viernes=prog_jue_vie
    )

    if fecha_timeout <= fecha_limite:
        return 0, fecha_limite

    # Contar días de desfase — sin excepciones de días
    dias_desfase = 0
    fecha_actual = fecha_limite + timedelta(days=1)
    while fecha_actual <= fecha_timeout:
        dias_desfase += 1
        fecha_actual += timedelta(days=1)

    return dias_desfase, fecha_limite
