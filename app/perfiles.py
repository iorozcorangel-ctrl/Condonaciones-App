"""
================================================================
  GESTIÓN DE PERFILES DE CONDONACIÓN
  Guarda, carga y gestiona los perfiles de configuración
================================================================
"""

import json, os
from app.config import (DIAS_PLAZO_PREVIO, DIAS_PLAZO_FERROMEX,
                        DIAS_PLAZO_CARRETERO, DIAS_LIMITE_SOLICITUD,
                        DIAS_LIMITE_PROGRAMACION)

ARCHIVO_PERFILES = os.path.join(os.path.dirname(__file__), "..", "perfiles.json")

PERFIL_DEFAULT = {
    "nombre":            "Default (Sin modificaciones)",
    "es_default":        True,
    "regla1_activa":     True,
    "regla2_activa":     True,
    "dias_previo":       DIAS_PLAZO_PREVIO,
    "dias_ferromex":     DIAS_PLAZO_FERROMEX,
    "dias_carretero":    DIAS_PLAZO_CARRETERO,
}


def cargar_perfiles():
    if not os.path.exists(ARCHIVO_PERFILES):
        return [PERFIL_DEFAULT]
    try:
        with open(ARCHIVO_PERFILES, "r", encoding="utf-8") as f:
            perfiles = json.load(f)
        if not any(p.get("es_default") for p in perfiles):
            perfiles.insert(0, PERFIL_DEFAULT)
        return perfiles
    except Exception:
        return [PERFIL_DEFAULT]


def guardar_perfiles(perfiles):
    try:
        with open(ARCHIVO_PERFILES, "w", encoding="utf-8") as f:
            json.dump(perfiles, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def agregar_perfil(perfil, perfiles):
    perfiles.append(perfil)
    guardar_perfiles(perfiles)
    return perfiles


def modificar_perfil(indice, perfil_nuevo, perfiles):
    if indice > 0:
        perfiles[indice] = perfil_nuevo
        guardar_perfiles(perfiles)
    return perfiles


def eliminar_perfil(indice, perfiles):
    if indice > 0:
        perfiles.pop(indice)
        guardar_perfiles(perfiles)
    return perfiles


def cargar_ultimo_perfil_usado():
    archivo = os.path.join(os.path.dirname(__file__), "..", "ultimo_perfil.json")
    try:
        with open(archivo, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("indice", 0)
    except Exception:
        return 0


def guardar_ultimo_perfil_usado(indice):
    archivo = os.path.join(os.path.dirname(__file__), "..", "ultimo_perfil.json")
    try:
        with open(archivo, "w", encoding="utf-8") as f:
            json.dump({"indice": indice}, f)
    except Exception:
        pass
