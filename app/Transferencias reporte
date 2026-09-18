"""
================================================================
  GENERADOR DEL DOCUMENTO FINAL — MÓDULO "TRANSFERENCIAS"
  Excel de 8 columnas empezando en la columna B (la columna A
  siempre queda vacía, porque el archivo se sube después a otra
  plataforma externa que da error si la columna A tiene contenido).
================================================================
"""

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from app.transferencias_config import (
    COLUMNAS_DOC_FINAL, TRUCKING_FIJO, ID_ESTADO_CONTENEDOR_FIJO,
)


def generar_documento_transferencias(filas, ruta_salida):
    """
    filas: lista de dicts, cada uno con las llaves:
        contenedor, id_solicitante, linea_op_texto, type_arch_iso,
        recinto_origen_codigo, recinto_destino_codigo
    ruta_salida: path o BytesIO donde se guarda el archivo.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Transferencias"

    hdr_font = Font(bold=True, name="Arial", size=10)
    dat_font = Font(name="Arial", size=10)
    center   = Alignment(horizontal="center", vertical="center")

    # ── Columna A: siempre vacía y angosta ───────────────────────
    ws.column_dimensions["A"].width = 4

    # ── Encabezados desde la columna B (col=2) ───────────────────
    for i, nombre_col in enumerate(COLUMNAS_DOC_FINAL):
        c = ws.cell(row=1, column=2 + i, value=nombre_col)
        c.font = hdr_font
        c.alignment = center
        ws.column_dimensions[c.column_letter].width = 18

    # ── Filas de datos ────────────────────────────────────────────
    for r, fila in enumerate(filas, start=2):
        valores = [
            fila.get("id_solicitante"),
            fila.get("contenedor"),
            fila.get("linea_op_texto"),
            fila.get("type_arch_iso"),
            fila.get("recinto_origen_codigo"),
            fila.get("recinto_destino_codigo"),
            ID_ESTADO_CONTENEDOR_FIJO,
            TRUCKING_FIJO,
        ]
        for i, val in enumerate(valores):
            c = ws.cell(row=r, column=2 + i, value=val)
            c.font = dat_font
            c.alignment = center

    ws.freeze_panes = "C2"
    ws.sheet_view.showGridLines = False

    wb.save(ruta_salida)
    return ruta_salida
