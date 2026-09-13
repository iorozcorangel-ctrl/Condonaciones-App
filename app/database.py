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
            "na_previo":      p.get("na_previo", False),
            "na_ffcc":        p.get("na_ffcc", False),
            "na_carretero":   p.get("na_carretero", False),
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
            "na_previo":      perfil.get("na_previo", False),
            "na_ffcc":        perfil.get("na_ffcc", False),
            "na_carretero":   perfil.get("na_carretero", False),
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
            "na_previo":      perfil.get("na_previo", False),
            "na_ffcc":        perfil.get("na_ffcc", False),
            "na_carretero":   perfil.get("na_carretero", False),
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


# ════════════════════════════════════════════════════════════════
#   GESTIÓN DE SESIONES PERSISTENTES
# ════════════════════════════════════════════════════════════════

DIAS_MAX_SESION = 2   # Duración absoluta máxima de la sesión (no se extiende)
MAX_SESIONES    = 3   # Máximo de sesiones simultáneas por usuario


def crear_sesion(usuario_id: str, username: str) -> str:
    """
    Crea una sesión en BD con expiración ABSOLUTA de DIAS_MAX_SESION días
    (no se extiende con la actividad). Además de esto, la persistencia real
    del navegador depende de una cookie de sesión (sin fecha de expiración)
    que el propio navegador borra al cerrarse por completo.
    """
    import secrets
    from datetime import datetime, timedelta
    try:
        db    = get_client()
        token = secrets.token_hex(32)
        ahora = datetime.utcnow()
        expira = ahora + timedelta(days=DIAS_MAX_SESION)

        # Limpiar sesiones ya vencidas del usuario
        db.table("sesiones").delete().eq(
            "usuario_id", usuario_id
        ).lt("expira_en", ahora.isoformat()).execute()

        # Verificar cuántas sesiones activas quedan
        res = db.table("sesiones").select("id, fecha_creacion").eq(
            "usuario_id", usuario_id
        ).order("fecha_creacion", desc=False).execute()
        sesiones_activas = res.data or []

        # Si ya hay MAX_SESIONES, eliminar la más antigua
        while len(sesiones_activas) >= MAX_SESIONES:
            mas_antigua = sesiones_activas.pop(0)
            db.table("sesiones").delete().eq("id", mas_antigua["id"]).execute()

        db.table("sesiones").insert({
            "usuario_id":       usuario_id,
            "token":            token,
            "username":         username,
            "expira_en":        expira.isoformat(),
            "ultima_actividad": ahora.isoformat(),
        }).execute()
        return token
    except Exception as e:
        # TEMPORAL: exponer el error real para diagnóstico
        return f"ERROR::{e}"


def verificar_sesion(token: str):
    """
    Verifica un token contra su expiración ABSOLUTA (fija desde la creación,
    máximo DIAS_MAX_SESION días). No se extiende con la actividad.
    """
    from datetime import datetime
    if not token:
        return None
    try:
        db  = get_client()
        res = db.table("sesiones").select(
            "id, usuario_id, username, expira_en"
        ).eq("token", token).execute()
        if not res.data:
            return None
        sesion = res.data[0]

        ahora  = datetime.utcnow()
        expira = datetime.fromisoformat(
            (sesion.get("expira_en") or "").replace("Z", "")
        )
        if ahora > expira:
            db.table("sesiones").delete().eq("token", token).execute()
            return None

        # Solo actualiza el timestamp informativo, no la expiración
        db.table("sesiones").update({
            "ultima_actividad": ahora.isoformat(),
        }).eq("token", token).execute()

        res2 = db.table("usuarios").select("*").eq(
            "id", sesion["usuario_id"]
        ).eq("activo", True).execute()
        return res2.data[0] if res2.data else None
    except Exception:
        return None


def eliminar_sesion(token: str):
    """Elimina una sesión (logout)."""
    if not token:
        return
    try:
        db = get_client()
        db.table("sesiones").delete().eq("token", token).execute()
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
#   BORRADORES DE PREVIO MANUAL
# ════════════════════════════════════════════════════════════════

def guardar_previo_borrador(usuario_id: str, numero_nc: str, contenedor: str,
                             previo_num: int, fecha_prog: str, fecha_pos: str):
    """Guarda o actualiza un previo individual en borrador."""
    try:
        db = get_client()
        from datetime import datetime
        datos = {
            "usuario_id":           usuario_id,
            "numero_nc":            numero_nc,
            "contenedor":           contenedor,
            "previo_num":           previo_num,
            "fecha_programacion":   fecha_prog or None,
            "fecha_posicionamiento": fecha_pos or None,
            "fecha_actualizacion":  datetime.utcnow().isoformat(),
        }
        db.table("borradores_previo").upsert(
            datos,
            on_conflict="usuario_id,numero_nc,contenedor,previo_num"
        ).execute()
        return True
    except Exception:
        return False


def cargar_borradores_previo(usuario_id: str, numero_nc: str):
    """Carga todos los borradores de previo para una NC."""
    try:
        db = get_client()
        res = db.table("borradores_previo").select("*").eq(
            "usuario_id", usuario_id
        ).eq("numero_nc", numero_nc).order("contenedor").order("previo_num").execute()
        return res.data or []
    except Exception:
        return []


def eliminar_borradores_nc(usuario_id: str, numero_nc: str):
    """Elimina todos los borradores de una NC al generar el reporte."""
    try:
        db = get_client()
        db.table("borradores_previo").delete().eq(
            "usuario_id", usuario_id
        ).eq("numero_nc", numero_nc).execute()
        return True
    except Exception:
        return False


def hay_borrador_activo(usuario_id: str, numero_nc: str):
    """Verifica si hay un borrador activo para esta NC."""
    try:
        db = get_client()
        res = db.table("borradores_previo").select("id").eq(
            "usuario_id", usuario_id
        ).eq("numero_nc", numero_nc).limit(1).execute()
        return len(res.data) > 0
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════
#   MÓDULO: ASIGNACIONES Y SEGUIMIENTO DE NC
# ════════════════════════════════════════════════════════════════

import re as _re


def extraer_contenedores(texto: str):
    """
    Extrae automáticamente contenedores válidos de un texto pegado,
    sin importar el separador (comas, sin separar, combinado).
    Formato: 3 letras + U + 7 dígitos = 11 caracteres.
    Máximo 300 contenedores.
    """
    if not texto:
        return []
    limpio = _re.sub(r'[^A-Za-z0-9]', '', texto.upper())
    encontrados = _re.findall(r'[A-Z]{3}U\d{7}', limpio)
    # Deduplicar conservando el orden
    vistos = []
    for c in encontrados:
        if c not in vistos:
            vistos.append(c)
    return vistos[:300]


# ── Motivos y Estatus (listas editables) ────────────────────────

def obtener_nc_motivos(solo_activos=True):
    try:
        db = get_client()
        q = db.table("nc_motivos").select("*").order("orden")
        if solo_activos:
            q = q.eq("activo", True)
        res = q.execute()
        return res.data or []
    except Exception:
        return []


def crear_nc_motivo(texto: str):
    try:
        db = get_client()
        max_orden = db.table("nc_motivos").select("orden").order("orden", desc=True).limit(1).execute()
        siguiente = (max_orden.data[0]["orden"] + 1) if max_orden.data else 1
        db.table("nc_motivos").insert({"texto": texto, "orden": siguiente}).execute()
        return True
    except Exception:
        return False


def editar_nc_motivo(motivo_id: str, texto: str):
    try:
        db = get_client()
        db.table("nc_motivos").update({"texto": texto}).eq("id", motivo_id).execute()
        return True
    except Exception:
        return False


def eliminar_nc_motivo(motivo_id: str):
    try:
        db = get_client()
        db.table("nc_motivos").update({"activo": False}).eq("id", motivo_id).execute()
        return True
    except Exception:
        return False


def obtener_nc_estatus(solo_activos=True):
    try:
        db = get_client()
        q = db.table("nc_estatus").select("*").order("orden")
        if solo_activos:
            q = q.eq("activo", True)
        res = q.execute()
        return res.data or []
    except Exception:
        return []


def crear_nc_estatus(texto: str, es_concluido=False):
    try:
        db = get_client()
        max_orden = db.table("nc_estatus").select("orden").order("orden", desc=True).limit(1).execute()
        siguiente = (max_orden.data[0]["orden"] + 1) if max_orden.data else 1
        db.table("nc_estatus").insert({
            "texto": texto, "orden": siguiente, "es_concluido": es_concluido
        }).execute()
        return True
    except Exception:
        return False


def editar_nc_estatus(estatus_id: str, texto: str, es_concluido=False):
    try:
        db = get_client()
        db.table("nc_estatus").update({
            "texto": texto, "es_concluido": es_concluido
        }).eq("id", estatus_id).execute()
        return True
    except Exception:
        return False


def eliminar_nc_estatus(estatus_id: str):
    try:
        db = get_client()
        db.table("nc_estatus").update({"activo": False}).eq("id", estatus_id).execute()
        return True
    except Exception:
        return False


# ── NC Asignaciones — CRUD principal ────────────────────────────

def crear_nc_asignacion(nc_externo: str, responsable_id: str, responsable_nombre: str,
                         fecha_solicitud: str, creado_por: str, vinculada_a: str = None):
    """Crea una nueva NC asignada. Retorna (True, id) o (False, error)."""
    try:
        db = get_client()
        res = db.table("nc_asignaciones").insert({
            "nc_externo":          nc_externo,
            "responsable_id":      responsable_id,
            "responsable_nombre":  responsable_nombre,
            "fecha_solicitud":     fecha_solicitud,
            "creado_por":          creado_por,
            "vinculada_a":         vinculada_a,
            "estado_visual":       "nuevo",
            "estatus":             "PENDIENTE DE REVISAR",
        }).execute()
        if res.data:
            nc_id = res.data[0]["id"]
            crear_nc_notificacion(
                responsable_id, nc_id,
                f"Se te asignó una nueva NC: {nc_externo}"
            )
            return True, nc_id
        return False, "No se pudo crear"
    except Exception as e:
        return False, str(e)


def obtener_nc_asignaciones(responsable_id: str = None, solo_activas: bool = None,
                             solo_concluidas: bool = None):
    """Obtiene NCs asignadas con filtros opcionales."""
    try:
        db = get_client()
        q = db.table("nc_asignaciones").select("*")
        if responsable_id:
            q = q.eq("responsable_id", responsable_id)
        if solo_concluidas is True:
            q = q.eq("concluida", True)
        elif solo_concluidas is False:
            q = q.eq("concluida", False)
        q = q.order("fecha_creacion", desc=True)
        res = q.execute()
        return res.data or []
    except Exception:
        return []


def obtener_nc_por_id(nc_id: str):
    try:
        db = get_client()
        res = db.table("nc_asignaciones").select("*").eq("id", nc_id).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


def actualizar_nc_asignacion(nc_id: str, datos: dict):
    """Actualiza campos de una NC asignada."""
    try:
        db = get_client()
        from datetime import datetime
        datos["fecha_actualizacion"] = datetime.utcnow().isoformat()
        db.table("nc_asignaciones").update(datos).eq("id", nc_id).execute()
        return True
    except Exception:
        return False


def reasignar_nc(nc_id: str, nuevo_responsable_id: str, nuevo_responsable_nombre: str):
    """Reasigna el responsable de una NC y notifica."""
    try:
        ok = actualizar_nc_asignacion(nc_id, {
            "responsable_id":     nuevo_responsable_id,
            "responsable_nombre": nuevo_responsable_nombre,
            "estado_visual":      "reasignado",
        })
        if ok:
            nc = obtener_nc_por_id(nc_id)
            crear_nc_notificacion(
                nuevo_responsable_id, nc_id,
                f"Se te reasignó la NC: {nc['nc_externo'] if nc else ''}"
            )
        return ok
    except Exception:
        return False


def inhabilitar_nc(nc_id: str, motivo: str):
    try:
        return actualizar_nc_asignacion(nc_id, {
            "inhabilitada": True,
            "motivo_inhabilitacion": motivo,
        })
    except Exception:
        return False


def marcar_seguimiento_nc(nc_id: str):
    """Cambia el estado visual a 'seguimiento' (verde) cuando el usuario abre/edita."""
    try:
        nc = obtener_nc_por_id(nc_id)
        if nc and nc.get("estado_visual") != "seguimiento":
            actualizar_nc_asignacion(nc_id, {"estado_visual": "seguimiento"})
    except Exception:
        pass


def concluir_nc(nc_id: str):
    try:
        return actualizar_nc_asignacion(nc_id, {"concluida": True})
    except Exception:
        return False


def reabrir_nc(nc_id: str):
    try:
        return actualizar_nc_asignacion(nc_id, {"concluida": False})
    except Exception:
        return False


def buscar_nc_asignaciones(termino: str):
    """Busca por NC externo, interno, contenedor o factura."""
    try:
        db = get_client()
        t = termino.strip().upper()
        res = db.table("nc_asignaciones").select("*").or_(
            f"nc_externo.ilike.%{t}%,"
            f"nc_interno.ilike.%{t}%,"
            f"contenedores.ilike.%{t}%,"
            f"numero_factura.ilike.%{t}%"
        ).execute()
        return res.data or []
    except Exception:
        return []


def actualizar_herencia_analisis(nc_asignacion_id: str, cliente: str, numero_factura: str):
    """Guarda Cliente y Factura provenientes del análisis en la NC asignada."""
    try:
        factura_limpia = _re.sub(r'[^0-9]', '', str(numero_factura)) if numero_factura else ""
        datos = {}
        if cliente:
            datos["cliente"] = cliente
        if factura_limpia:
            datos["numero_factura"] = factura_limpia
        if datos:
            actualizar_nc_asignacion(nc_asignacion_id, datos)
        return True
    except Exception:
        return False


# ── Notificaciones ───────────────────────────────────────────────

def crear_nc_notificacion(usuario_id: str, nc_id: str, mensaje: str):
    try:
        db = get_client()
        db.table("nc_notificaciones").insert({
            "usuario_id": usuario_id,
            "nc_id": nc_id,
            "mensaje": mensaje,
        }).execute()
        return True
    except Exception:
        return False


def obtener_notificaciones_pendientes(usuario_id: str):
    try:
        db = get_client()
        res = db.table("nc_notificaciones").select("*").eq(
            "usuario_id", usuario_id
        ).eq("vista", False).order("fecha_creacion", desc=True).execute()
        return res.data or []
    except Exception:
        return []


def marcar_notificaciones_vistas(usuario_id: str):
    try:
        db = get_client()
        db.table("nc_notificaciones").update({"vista": True}).eq(
            "usuario_id", usuario_id
        ).eq("vista", False).execute()
        return True
    except Exception:
        return False


# ── Detección de contenedores duplicados entre NCs ──────────────

def verificar_contenedores_en_nc(contenedores: list, excluir_nc_id: str = None):
    """
    Busca si alguno de los contenedores ya existe en otra NC asignada.
    Retorna lista de coincidencias: [{nc_id, nc_externo, contenedor,
    responsable_nombre, concluida, inhabilitada}]
    """
    try:
        db = get_client()
        res = db.table("nc_asignaciones").select(
            "id, nc_externo, contenedores, responsable_nombre, concluida, inhabilitada"
        ).execute()
        todas = res.data or []
        coincidencias = []
        for nc in todas:
            if excluir_nc_id and nc["id"] == excluir_nc_id:
                continue
            if nc.get("inhabilitada"):
                continue
            conts_nc = (nc.get("contenedores") or "").split(",")
            conts_nc = [c.strip() for c in conts_nc if c.strip()]
            for c in contenedores:
                if c in conts_nc:
                    coincidencias.append({
                        "nc_id":              nc["id"],
                        "nc_externo":         nc["nc_externo"],
                        "contenedor":         c,
                        "responsable_nombre": nc.get("responsable_nombre", ""),
                        "concluida":          nc.get("concluida", False),
                    })
        return coincidencias
    except Exception:
        return []


def registrar_duplicado_revisado(nc_id: str, contenedor: str, revisado_por: str):
    try:
        db = get_client()
        db.table("nc_duplicados_revisados").insert({
            "nc_id": nc_id,
            "contenedor": contenedor,
            "revisado_por": revisado_por,
        }).execute()
        return True
    except Exception:
        return False
