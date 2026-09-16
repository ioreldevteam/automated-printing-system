"""Universal Label Designer and Multi-Printer Template Engine.

Supports:
1. Zebra Printers: Native ZPL II template generation (^XA...^XZ).
2. ANSER X1 Printers: 1-bit monochrome bitmap (.bmp) generation and dynamic FIFO serial push.
3. Windows / CUPS / General Printers: High-resolution PNG / BMP / QImage rendering with WYSIWYG accuracy.

Layout matches the industrial standard label specification:
- Outer rectangular border with inner section grid
- Left Column: 1D Retail Barcode, Batch Code, MRP Value
- Center Column: Item Description, SLS Certification Mark, Rated Current/Voltage, Item Code
- Right Column: Dynamic QR Code with human-readable Serial Number underneath
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication

from app.domain.models import LabelData
from app.printers.barcode_generator import encode_code128, generate_qr_matrix


def _ensure_gui_app() -> None:
    if QApplication.instance() is None:
        # Standalone or headless execution requires a QApplication for font metrics & widgets
        QApplication(["app", "-platform", "offscreen"])


def _extract_field(data: LabelData | dict[str, Any], key: str, default: str = "") -> str:
    if isinstance(data, dict):
        val = data.get(key)
        if val is None:
            # Check lowercase or alternate key
            val = data.get(key.lower(), default)
        return str(val) if val is not None else default
    if hasattr(data, key.lower()):
        val = getattr(data, key.lower())
        if val:
            return str(val)
    if hasattr(data, "extra") and isinstance(data.extra, dict):
        val = data.extra.get(key) or data.extra.get(key.lower())
        if val is not None:
            return str(val)
    # Default fallbacks
    fallbacks = {
        "PRODUCT_NAME": getattr(data, "product_name", default),
        "SERIAL_NUMBER": getattr(data, "serial_number", default),
        "BATCH_CODE": getattr(data, "batch_number", default),
        "BATCH_NUMBER": getattr(data, "batch_number", default),
    }
    return str(fallbacks.get(key, default))


def render_label_qimage(
    data: LabelData | dict[str, Any],
    width: int = 600,
    height: int = 240,
) -> QImage:
    """Render a pixel-perfect label QImage matching the official print guideline."""
    _ensure_gui_app()
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    pen_thick = QPen(QColor("black"), 3)
    pen_thin = QPen(QColor("black"), 2)
    painter.setPen(pen_thick)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    # 1. Outer Border
    border_x, border_y, border_w, border_h = 10, 10, 580, 220
    painter.drawRect(border_x, border_y, border_w, border_h)

    # 2. Main Column Dividers
    col1_x = 230  # Left | Center
    col2_x = 445  # Center | Right
    painter.drawLine(col1_x, border_y, col1_x, border_y + border_h)
    painter.drawLine(col2_x, border_y, col2_x, border_y + border_h)

    # 3. Left Column Dividers
    left_row1_y = 125  # Below barcode
    left_row2_y = 172  # Below batch code
    painter.drawLine(border_x, left_row1_y, col1_x, left_row1_y)
    painter.drawLine(border_x, left_row2_y, col1_x, left_row2_y)

    # 4. Center Column Dividers
    center_row1_y = 125  # Below item description
    center_subcol_x = 305  # SLS | Specs & Item Code
    center_subrow_y = 172  # Specs | Item Code
    painter.drawLine(col1_x, center_row1_y, col2_x, center_row1_y)
    painter.drawLine(center_subcol_x, center_row1_y, center_subcol_x, border_y + border_h)
    painter.drawLine(center_subcol_x, center_subrow_y, col2_x, center_subrow_y)

    # ==========================
    # DATA EXTRACTION
    # ==========================
    product_name = _extract_field(data, "PRODUCT_NAME", "1 Gang 1 Way Switch Indicator")
    retail_barcode = _extract_field(data, "RETAIL_BARCODE", "8901234567890")
    batch_code = _extract_field(data, "BATCH_CODE", "BATCH-20260916-01")
    mrp_value = _extract_field(data, "MRP_VALUE", "450.00")
    rated_specs = _extract_field(data, "RATED_SPECS", "10 AX / 250 V~")
    item_code = _extract_field(data, "ITEM_CODE", "101-1001")
    sls_code = _extract_field(data, "SLS_CODE", "141")
    serial_number = _extract_field(data, "SERIAL_NUMBER", "SN1011001-0001")

    # ==========================
    # LEFT COLUMN RENDERING
    # ==========================
    # A) 1D Retail Barcode
    barcode_modules = encode_code128(retail_barcode)
    bar_w = 1.15
    start_bar_x = border_x + 12
    bar_y = border_y + 12
    bar_h = 75

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor("black")))
    for idx, bit in enumerate(barcode_modules):
        if bit == "1":
            x_pos = start_bar_x + (idx * bar_w)
            painter.drawRect(QRectF(x_pos, bar_y, bar_w, bar_h))

    # Barcode text underneath
    painter.setPen(QPen(QColor("black")))
    font_barcode = QFont("monospace", 10, QFont.Weight.Bold)
    painter.setFont(font_barcode)
    painter.drawText(QRect(border_x, bar_y + bar_h + 2, col1_x - border_x, 22),
                     Qt.AlignmentFlag.AlignCenter, retail_barcode)

    # B) Batch code
    font_batch = QFont("sans-serif", 10, QFont.Weight.DemiBold)
    painter.setFont(font_batch)
    painter.drawText(QRect(border_x + 6, left_row1_y + 2, col1_x - border_x - 12, left_row2_y - left_row1_y),
                     Qt.AlignmentFlag.AlignCenter, batch_code)

    # C) MRP Value
    font_mrp = QFont("sans-serif", 11, QFont.Weight.Bold)
    painter.setFont(font_mrp)
    mrp_text = f"MRP RS. {float(mrp_value):.2f}" if mrp_value.replace(".", "", 1).isdigit() else f"MRP RS. {mrp_value}"
    painter.drawText(QRect(border_x + 6, left_row2_y + 2, col1_x - border_x - 12, border_y + border_h - left_row2_y),
                     Qt.AlignmentFlag.AlignCenter, mrp_text)

    # ==========================
    # CENTER COLUMN RENDERING
    # ==========================
    # A) Item Description (top)
    font_desc = QFont("sans-serif", 12, QFont.Weight.Bold)
    painter.setFont(font_desc)
    painter.drawText(QRect(col1_x + 8, border_y + 12, col2_x - col1_x - 16, center_row1_y - border_y - 20),
                     Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, product_name)

    # B) SLS Certification Mark (bottom-left)
    # Outer rounded box
    sls_rect = QRectF(col1_x + 12, center_row1_y + 10, 52, 48)
    painter.setPen(pen_thin)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(sls_rect, 6, 6)

    # Stylized SLS text
    font_sls = QFont("sans-serif", 14, QFont.Weight.ExtraBold)
    painter.setFont(font_sls)
    painter.drawText(QRect(col1_x + 12, center_row1_y + 18, 52, 28),
                     Qt.AlignmentFlag.AlignCenter, "SLS")

    # SLS Code under box
    font_sls_code = QFont("sans-serif", 8, QFont.Weight.Bold)
    painter.setFont(font_sls_code)
    painter.drawText(QRect(col1_x + 4, center_row1_y + 62, 68, 20),
                     Qt.AlignmentFlag.AlignCenter, sls_code)

    # C) Rated Current & Voltage (bottom-right upper)
    font_specs = QFont("sans-serif", 11, QFont.Weight.DemiBold)
    painter.setFont(font_specs)
    painter.drawText(QRect(center_subcol_x + 6, center_row1_y + 4, col2_x - center_subcol_x - 12, center_subrow_y - center_row1_y),
                     Qt.AlignmentFlag.AlignCenter, rated_specs)

    # D) Item Code (bottom-right lower)
    font_code = QFont("sans-serif", 13, QFont.Weight.Bold)
    painter.setFont(font_code)
    painter.drawText(QRect(center_subcol_x + 6, center_subrow_y + 4, col2_x - center_subcol_x - 12, border_y + border_h - center_subrow_y),
                     Qt.AlignmentFlag.AlignCenter, item_code)

    # ==========================
    # RIGHT COLUMN RENDERING (DYNAMIC QR & SERIAL)
    # ==========================
    qr_matrix = generate_qr_matrix(serial_number)
    qr_size = len(qr_matrix)
    cell_size = 3.6  # approx 90px x 90px
    qr_top_x = col2_x + 22
    qr_top_y = border_y + 16

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor("black")))
    for r in range(qr_size):
        for c in range(qr_size):
            if qr_matrix[r][c]:
                painter.drawRect(QRectF(qr_top_x + (c * cell_size),
                                        qr_top_y + (r * cell_size),
                                        cell_size, cell_size))

    # Serial Number Text underneath QR
    painter.setPen(QPen(QColor("black")))
    font_serial = QFont("monospace", 8, QFont.Weight.Bold)
    painter.setFont(font_serial)
    painter.drawText(QRect(col2_x + 4, border_y + border_h - 32, border_x + border_w - col2_x - 8, 26),
                     Qt.AlignmentFlag.AlignCenter, serial_number)

    painter.end()
    return image


def save_label_png(data: LabelData | dict[str, Any], output_path: str | Path) -> str:
    """Render and save label as a high-resolution 24-bit PNG."""
    image = render_label_qimage(data)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(target), "PNG")
    return str(target)


def save_label_monochrome_bmp(data: LabelData | dict[str, Any], output_path: str | Path) -> str:
    """Render and save label as a 1-bit monochrome BMP (ideal for Anser X1 TIJ image mode)."""
    image = render_label_qimage(data)
    mono_image = image.convertToFormat(QImage.Format.Format_Mono, Qt.ImageConversionFlag.MonoOnly)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    mono_image.save(str(target), "BMP")
    return str(target)


def generate_zebra_zpl(data: LabelData | dict[str, Any]) -> str:
    """Generate the exact native ZPL II string for Zebra printers."""
    product_name = _extract_field(data, "PRODUCT_NAME", "1 Gang 1 Way Switch Indicator")
    retail_barcode = _extract_field(data, "RETAIL_BARCODE", "8901234567890")
    batch_code = _extract_field(data, "BATCH_CODE", "BATCH-20260916-01")
    mrp_value = _extract_field(data, "MRP_VALUE", "450.00")
    rated_specs = _extract_field(data, "RATED_SPECS", "10 AX / 250 V~")
    item_code = _extract_field(data, "ITEM_CODE", "101-1001")
    sls_code = _extract_field(data, "SLS_CODE", "141")
    serial_number = _extract_field(data, "SERIAL_NUMBER", "SN1011001-0001")

    mrp_display = f"MRP RS. {float(mrp_value):.2f}" if mrp_value.replace(".", "", 1).isdigit() else f"MRP RS. {mrp_value}"

    return f"""^XA
^PW600
^LL240
^PON

; Outer border (580 x 220, 3 dots)
^FO10,10^GB580,220,3^FS

; Column Dividers
^FO230,10^GB3,220,3^FS
^FO445,10^GB3,220,3^FS

; Left Column Dividers
^FO10,125^GB220,3,3^FS
^FO10,172^GB220,3,3^FS

; Left: 1D Retail Barcode (Code 128)
^FO22,22^BY2,2,65^BCN,65,Y,N,N^FD{retail_barcode}^FS

; Left: Batch Code
^FO15,140^A0N,20,20^FB210,1,0,C^FD{batch_code}^FS

; Left: MRP Value
^FO15,188^A0N,22,22^FB210,1,0,C^FD{mrp_display}^FS

; Center Column Dividers
^FO230,125^GB215,3,3^FS
^FO305,125^GB3,105,3^FS
^FO305,172^GB140,3,3^FS

; Center: Item Description
^FO235,30^A0N,24,24^FB205,3,0,C^FD{product_name}^FS

; Center: SLS Certification Box & Text
^FO242,135^GB52,46,2,B,6^FS
^FO245,143^A0N,22,22^FB46,1,0,C^FDSLS^FS
^FO235,192^A0N,18,18^FB65,1,0,C^FD{sls_code}^FS

; Center: Rated Current & Voltage
^FO310,140^A0N,20,20^FB130,1,0,C^FD{rated_specs}^FS

; Center: Item Code (xxx-xxxx)
^FO310,188^A0N,24,24^FB130,1,0,C^FD{item_code}^FS

; Right: Dynamic QR Code
^FO465,22^BQN,2,4^FDQA,{serial_number}^FS

; Right: Serial Number text under QR code
^FO450,192^A0N,16,16^FB135,1,0,C^FD{serial_number}^FS

^XZ"""
