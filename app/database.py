"""
================================================================
  MÓDULO DE BASE DE DATOS — Supabase
  Maneja todas las operaciones con la base de datos
================================================================
"""

import streamlit as st
from supabase import create_client, Client
import hashlib
import secrets
import re
from datetime import datetime


def get_client() -> Client:
    url  = st.secrets["SUPABASE_URL"]
    key  = st.secrets["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


# ── Hash de contraseña ──────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = "condonaciones_salt_2026"
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def verificar_password(password: str, hash_guardado: str) -> bool:
    return hash_password(password) == hash_guardado


# ════════════════════════════════════════════════════════════════
#   USUARIOS
# ════════════════════════════════════════════════════════════════

def login_usuario(username: str, password: str):
    """Retorna el usuario si las credenciales son correctas, None si no."""
    try:
        db = get_client()
        res = db.table("usuarios").select("*").eq("username", username).eq("activo", True).execute()
        if not res.data:
            return None
        usuario = res.data[0]
        if verificar_password(password, usuario["password_hash"]):
            return usuario
        return None
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None


def obtener_usuarios():
    """Retorna todos los usuarios activos."""
    try:
        db = get_client()
        res = db.table("usuarios").select("id, username, nombre_completo, rol, activo, fecha_creacion").order("fecha_creacion").execute()
        return res.data or []
    except Exception:
        return []


def crear_usuario(username: str, password: str, nombre_completo: str, rol: str):
    """Crea un nuevo usuario. Retorna (True, msg) o (False, error)."""
    try:
        db = get_client()
        # Verificar que no exista
        existe = db.table("usuarios").select("id").eq("username", username).execute()
        if existe.data:
            return False, f"El usuario '{username}' ya existe"
        db.table("usuarios").insert({
            "username":        username,
            "password_hash":   hash_password(password),
            "nombre_completo": nombre_completo,
            "rol":             rol,
            "activo":          True,
        }).execute()
        return True, "Usuario creado correctamente"
    except Exception as e:
        return False, str(e)


def cambiar_password(usuario_id: str, nueva_password: str):
    """Cambia la contraseña de un usuario."""
    try:
        db = get_client()
        db.table("usuarios").update({
            "password_hash": hash_password(nueva_password)
        }).eq("id", usuario_id).execute()
        return True, "Contraseña actualizada"
    except Exception as e:
        return False, str(e)


def toggle_usuario(usuario_id: str, activo: bool):
    """Activa o desactiva un usuario."""
    try:
        db = get_client()
        db.table("usuarios").update({"activo": activo}).eq("id", usuario_id).execute()
        return True
    except Exception:
        return False


def eliminar_usuario(usuario_id: str):
    """Elimina un usuario permanentemente."""
    try:
        db = get_client()
        db.table("usuarios").delete().eq("id", usuario_id).execute()
        return True
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════
#   HISTORIAL DE NCs
# ════════════════════════════════════════════════════════════════

def registrar_nc(numero_nc: str, usuario_id: str, usuario_nombre: str,
                 contenedores: list, facturas: list, monto_total: float):
    """
    Registra una NC en el historial y sus detalles.
    contenedores: lista de strings con números de contenedor
    facturas: lista de strings con números de factura
    """
    try:
        db = get_client()

        # Insertar en historial_nc
        res = db.table("historial_nc").insert({
            "numero_nc":          numero_nc,
            "usuario_id":         usuario_id,
            "usuario_nombre":     usuario_nombre,
            "total_contenedores": len(contenedores),
            "monto_total":        monto_total,
        }).execute()

        if not res.data:
            return False, "Error al registrar la NC"

        nc_id = res.data[0]["id"]

        # Insertar detalles por contenedor — solo filas con contenedor válido
        detalles = []
        for i, cont in enumerate(contenedores):
            # Limpiar contenedor
            cont_limpio = str(cont).strip().upper() if cont else ""
            if not cont_limpio or cont_limpio.lower() in ("nan", "none", ""):
                continue

            # Limpiar factura — quitar decimales si viene como float
            factura = facturas[i] if i < len(facturas) else None
            if factura is not None:
                factura_str = str(factura).strip()
                if factura_str.lower() in ("nan", "none", "", "0", "0.0"):
                    factura_str = None
                elif factura_str.endswith(".0"):
                    factura_str = factura_str[:-2]
            else:
                factura_str = None

            detalles.append({
                "historial_nc_id": nc_id,
                "numero_nc":       numero_nc,
                "contenedor":      cont_limpio,
                "numero_factura":  factura_str,
            })

        if detalles:
            db.table("detalle_nc").insert(detalles).execute()

        return True, "NC registrada correctamente"
    except Exception as e:
        return False, str(e)


def verificar_duplicados(contenedores: list, facturas: list):
    """
    Verifica si alguna factura o contenedor ya existe en otra NC registrada.
    Retorna lista de duplicados encontrados.
    """
    duplicados = []
    try:
        db = get_client()

        # Limpiar facturas — eliminar nulos, nan, None, vacíos
        facturas_limpias = []
        for f in facturas:
            if f is None:
                continue
            s = str(f).strip()
            if s.lower() in ("nan", "none", "", "0", "0.0"):
                continue
            # Limpiar decimales de números que vienen como float
            if s.endswith(".0"):
                s = s[:-2]
            facturas_limpias.append(s)

        # Limpiar contenedores
        contenedores_limpios = [str(c).strip().upper()
                                for c in contenedores
                                if c and str(c).strip().lower() not in ("nan","none","")]

        # ── Verificar por factura ──────────────────────────────
        facturas_unicas = list(set(facturas_limpias))
        for factura in facturas_unicas:
            res = db.table("detalle_nc").select(
                "numero_factura, numero_nc, fecha_creacion, contenedor"
            ).eq("numero_factura", factura).execute()

            if res.data:
                for reg in res.data:
                    duplicados.append({
                        "tipo":        "Factura",
                        "valor":       factura,
                        "nc_anterior": reg["numero_nc"],
                        "contenedor":  reg.get("contenedor", ""),
                        "fecha":       reg["fecha_creacion"][:10] if reg["fecha_creacion"] else ""
                    })

        # ── Verificar por contenedor ───────────────────────────
        contenedores_unicos = list(set(contenedores_limpios))
        for cont in contenedores_unicos:
            res = db.table("detalle_nc").select(
                "contenedor, numero_nc, fecha_creacion, numero_factura"
            ).eq("contenedor", cont).execute()

            if res.data:
                for reg in res.data:
                    # Evitar duplicar si ya se detectó por factura
                    ya_registrado = any(
                        d["nc_anterior"] == reg["numero_nc"] and d["valor"] == cont
                        for d in duplicados
                    )
                    if not ya_registrado:
                        duplicados.append({
                            "tipo":        "Contenedor",
                            "valor":       cont,
                            "nc_anterior": reg["numero_nc"],
                            "contenedor":  cont,
                            "fecha":       reg["fecha_creacion"][:10] if reg["fecha_creacion"] else ""
                        })

        return duplicados

    except Exception as e:
        # Retornar el error para que pueda mostrarse en la interfaz
        return [{"tipo": "ERROR", "valor": str(e), "nc_anterior": "", "contenedor": "", "fecha": ""}]


def obtener_historial(limite: int = 2000):
    """Retorna el historial de NCs ordenado por fecha descendente."""
    try:
        db = get_client()
        res = db.table("historial_nc").select(
            "id, numero_nc, usuario_nombre, fecha_creacion, total_contenedores, monto_total"
        ).order("fecha_creacion", desc=True).limit(limite).execute()
        return res.data or []
    except Exception:
        return []


def obtener_detalle_nc(nc_id: str):
    """Retorna el detalle de contenedores y facturas de una NC."""
    try:
        db = get_client()
        res = db.table("detalle_nc").select(
            "contenedor, numero_factura"
        ).eq("historial_nc_id", nc_id).execute()
        return res.data or []
    except Exception:
        return []


def eliminar_nc(nc_id: str):
    """Elimina una NC y su detalle (solo admin)."""
    try:
        db = get_client()
        db.table("historial_nc").delete().eq("id", nc_id).execute()
        return True
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════
#   PERFILES DE CONDONACIÓN
# ════════════════════════════════════════════════════════════════

def obtener_perfiles():
    """Retorna todos los perfiles ordenados: default primero."""
    try:
        db = get_client()
        res = db.table("perfiles").select("*").order("es_default", desc=True).order("fecha_creacion").execute()
        data = res.data or []
        # Convertir a formato compatible con el sistema actual
        return [{
            "id":             p["id"],
            "nombre":         p["nombre"],
            "es_default":     p["es_default"],
            "regla1_activa":  p["regla1_activa"],
            "regla2_activa":  p["regla2_activa"],
            "dias_previo":    p["dias_previo"],
            "dias_ferromex":  p["dias_ferromex"],
            "dias_carretero": p["dias_carretero"],
        } for p in data]
    except Exception:
        # Fallback al perfil default si falla la conexión
        return [{
            "nombre": "Default (Sin modificaciones)",
            "es_default": True,
            "regla1_activa": True,
            "regla2_activa": True,
            "dias_previo": 3,
            "dias_ferromex": 3,
            "dias_carretero": 2,
        }]


def crear_perfil_db(perfil: dict):
    """Crea un nuevo perfil en la base de datos."""
    try:
        db = get_client()
        res = db.table("perfiles").insert({
            "nombre":         perfil["nombre"],
            "es_default":     False,
            "regla1_activa":  perfil.get("regla1_activa", True),
            "regla2_activa":  perfil.get("regla2_activa", True),
            "dias_previo":    perfil.get("dias_previo", 3),
            "dias_ferromex":  perfil.get("dias_ferromex", 3),
            "dias_carretero": perfil.get("dias_carretero", 2),
        }).execute()
        return True, res.data[0] if res.data else {}
    except Exception as e:
        return False, str(e)


def modificar_perfil_db(perfil_id: str, perfil: dict):
    """Modifica un perfil existente."""
    try:
        db = get_client()
        db.table("perfiles").update({
            "nombre":         perfil["nombre"],
            "regla1_activa":  perfil.get("regla1_activa", True),
            "regla2_activa":  perfil.get("regla2_activa", True),
            "dias_previo":    perfil.get("dias_previo", 3),
            "dias_ferromex":  perfil.get("dias_ferromex", 3),
            "dias_carretero": perfil.get("dias_carretero", 2),
        }).eq("id", perfil_id).execute()
        return True
    except Exception:
        return False


def eliminar_perfil_db(perfil_id: str):
    """Elimina un perfil de la base de datos."""
    try:
        db = get_client()
        db.table("perfiles").delete().eq("id", perfil_id).execute()
        return True
    except Exception:
        return False


def guardar_ultimo_perfil_db(usuario_id: str, perfil_id: str):
    """Guarda el último perfil usado por el usuario."""
    try:
        db = get_client()
        # Usar upsert en tabla usuarios para guardar ultimo_perfil_id
        db.table("usuarios").update(
            {"ultimo_perfil_id": perfil_id}
        ).eq("id", usuario_id).execute()
        return True
    except Exception:
        return False


def obtener_ultimo_perfil_db(usuario_id: str):
    """Obtiene el último perfil usado por el usuario."""
    try:
        db = get_client()
        res = db.table("usuarios").select("ultimo_perfil_id").eq("id", usuario_id).execute()
        if res.data and res.data[0].get("ultimo_perfil_id"):
            return res.data[0]["ultimo_perfil_id"]
        return None
    except Exception:
        return None
