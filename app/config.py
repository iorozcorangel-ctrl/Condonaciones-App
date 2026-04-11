"""
================================================================
  CONFIGURACIÓN GENERAL — Colores, constantes y festivos
  Para modificar parámetros del programa editar este archivo
================================================================
"""

# ── Colores de la interfaz ──────────────────────────────────────
COLORES = {
    "azul_oscuro":   "#1F4E79",
    "azul_medio":    "#2E75B6",
    "azul_claro":    "#D6E4F0",
    "blanco":        "#FFFFFF",
    "gris_claro":    "#F5F5F5",
    "gris_medio":    "#E0E0E0",
    "gris_texto":    "#666666",
    "verde":         "#2E7D32",
    "verde_claro":   "#E8F5E9",
    "naranja":       "#E65100",
    "naranja_claro": "#FFF3E0",
    "amarillo":      "#F57F17",
    "amarillo_claro":"#FFFDE7",
    "rojo":          "#C62828",
    "rojo_claro":    "#FFEBEE",
    "azul_rango":    "#E3F2FD",
    "texto_primary": "#212121",
    "texto_secondary":"#757575",
}

# ── Fuentes ─────────────────────────────────────────────────────
FUENTE_TITULO  = ("Segoe UI", 14, "bold")
FUENTE_SUBTIT  = ("Segoe UI", 11, "bold")
FUENTE_NORMAL  = ("Segoe UI", 10)
FUENTE_SMALL   = ("Segoe UI", 9)
FUENTE_BOLD    = ("Segoe UI", 10, "bold")

# ── Días festivos oficiales México (Ley Federal del Trabajo) ────
# Formato: (mes, dia) — aplican todos los años
FESTIVOS_FIJOS = [
    (1,  1),   # Año Nuevo
    (2,  5),   # Día de la Constitución (primer lunes febrero — aprox)
    (3,  21),  # Natalicio de Benito Juárez
    (5,  1),   # Día del Trabajo
    (9,  16),  # Independencia de México
    (11, 20),  # Revolución Mexicana
    (12, 25),  # Navidad
]

# Festivos con fecha exacta por año {año: [(mes, dia), ...]}
FESTIVOS_VARIABLES = {
    2024: [(2, 5), (11, 18)],
    2025: [(2, 3), (11, 17)],
    2026: [(2, 2), (11, 16)],
    2027: [(2, 1), (11, 15)],
    2028: [(2, 7), (11, 20)],
    2029: [(2, 5), (11, 19)],
    2030: [(2, 4), (11, 18)],
}

# ── Parámetros de reglas de negocio (perfil Default) ───────────
DIAS_PLAZO_PREVIO      = 3   # Regla 3
DIAS_PLAZO_FERROMEX    = 3   # Regla 4
DIAS_PLAZO_CARRETERO   = 2   # Regla 5
DIAS_LIMITE_SOLICITUD  = 30  # Regla 1
DIAS_LIMITE_PROGRAMACION = 4 # Regla 2

# ── Columnas del Tabulador Comercial ───────────────────────────
COL_TAB = {
    "contenedor":  "CONTENEDOR",
    "importe":     "IMPORTE SIN IVA A CONDONAR",
    "clabe":       "CLABE INTERBANCARIA",
    "no_bl":       "No. BL",
    "arribo":      "FECHA DE ARRIBO A LA TERMINAL",
    "liner_no":    "LINER/ NO LINER",
    "naviera":     "NAVIERA",
    "tipo_cont":   "TIPO DE CONTENEDOR",
    "sobredim":    "SOBREDIMENSIONADO",
    "peligroso":   "PELIGROSO",
    "flat_rack":   "FLAT RACK",
    "refrigerado": "REFRIGERADO",
    "no_factura":  "No. FACTURA",
    "conceptos":   "CONCEPTOS A CONDONAR",
    "agencia":     "AGENCIA ADUANAL",
    "cliente":     "CLIENTE",
}

# ── Columnas del Archivo BI ─────────────────────────────────────
COL_BI = {
    "folios":           "Folios",
    "contenedor":       "Contenedor",
    "procede":          "Procede/NOProcede",
    "liner":            "Liner",
    "line_op":          "Line OP",
    "time_in":          "TimeIn",
    "dia_time_in":      "Dia Time In",
    "fecha_revalidado": "FechaRevalidado",
    "dia_revalidado":   "Dia Revalidado",
    "fecha_previo":     "FechaSolitudPrevio",
    "dia_previo":       "Dia Previo",
    "no_servicios":     "No. Servicios",
    "fecha_cmsa_previo":"FechaCMSAPrevio",
    "dia_cmsa_previo":  "Dia CMSA Previo",
    "paso_2_dias":      "Pasó de los 2 días habiles operables",
    "fecha_posicion":   "FechaPosicionamiento",
    "dia_posicion":     "Dia Posicionamiento",
    "fecha_cancel":     "FechaCancelacion",
    "dia_cancel":       "Dia Cancelacion",
    "no_services_order":"No. Services Order",
    "dias_desfase_previo": "Cuántos días de desfase en previo?",
    "dias_intento":     "Cuántos días de intentó de programación desde que se inició",
    "fecha_liberacion": "Fecha de Liberacion",
    "dia_liberacion":   "Dia Liberacion",
    "no_liberaciones":  "No. Liberaciones",
    "ffcc":             "FFCC",
    "fecha_ferromex":   "FechaFerroMex",
    "dia_ferromex":     "Dia FerroMex",
    "paso_3_ffcc":      "Pasó de los 3 días para cargar a FFCC",
    "fecha_gondola":    "Fecha Gondola",
    "dia_gondola":      "Dia Gondola",
    "fecha_entrega":    "Fecha de programación de entrega",
    "dia_entrega":      "Dia Entrega",
    "no_entregas":      "No. Entregas",
    "no_appt":          "No. Appt",
    "fecha_auth_naviera":"Fecha de autorización de solicitud por La naviera (en caso de que si es liner)",
    "fecha_cmsa_entrega":"Fecha otorgada por CMSA para la entrega",
    "dia_entrega_cmsa": "Dia Entrega CMSA",
    "time_out":         "TimeOut",
    "dia_time_out":     "Dia Time Out",
    "dias_desfase_entrega": "Cuántos días de desfase en entrega?",
    "comentarios":      "Comentarios",
    "tipo_contenedor":  "Tipo de contenedor",
    "is_oog":           "IsOOG",
    "is_hazardous":     "IsHazardous",
    "alm_qty":          "Almacenaje Qty",
    "alm_subtotal":     "Almacenaje SubTotal",
    "dias_alm_cobrar":  "DIAS DE ALMACENAJE A COBRAR",
    "dias_proceden":    "Cuantos dias le proceden para cobro",
    "energia_qty":      "Suministro De Energía Qty",
    "energia_subtotal": "Suministro De Energía SubTotal",
    "no_show_qty":      "No Show Qty",
    "no_show_subtotal": "No Show SubTotal",
    "dias_conex_cond":  "Dias de conexiones a condonar",
    "dias_resp_cms":    "Días responsabilidad de CMS  (días a condonar de conexión)",
    "remanejo_qty":     "Remanejo Por Cambio De Buque Qty",
    "remanejo_subtotal":"Remanejo Por Cambio De Buque SubTotal",
    "admon_qty":        "Servicio de Administración y Control Qty",
    "admon_subtotal":   "Servicio de Administración y Control SubTotal",
    "monto_alm":        "Monto a condonar por almacenaje",
    "monto_conex":      "Monto a condonar por conexiones",
    "monto_maniobra":   "Monto a condonar por maniobra no realizada",
    "monto_admon":      "Monto a condonar por servicio de admon y control",
    "no_factura":       "No. Factura",
    "billing":          "Billing condonaciones",
    "nc_folio":         "NC.Folio",
    "alm_qty_nc":       "Almacenaje Qty NC",
    "alm_subtotal_nc":  "Almacenaje SubTotal NC",
    "admon_qty_nc":     "Servicio de Administración y Control Qty NC",
    "admon_subtotal_nc":"Servicio de Administración y Control SubTotal NC",
    "agente_aduanal":   "Agente Aduanal",
    "cliente":          "Cliente",
    "monto_total":      "Monto Total",
    "notas_credito":    "Notas de Credito",
}

# ── Color encabezado reporte Excel ─────────────────────────────
HEADER_COLOR_REPORTE = "2E8B72"  # Verde azulado
