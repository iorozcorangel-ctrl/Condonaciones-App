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

        # Insertar detalles por contenedor
        detalles = []
        for i, cont in enumerate(contenedores):
            factura = facturas[i] if i < len(facturas) else None
            detalles.append({
                "historial_nc_id": nc_id,
                "numero_nc":       numero_nc,
                "contenedor":      cont,
                "numero_factura":  str(factura) if factura and str(factura) not in ("nan", "None", "") else None,
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
