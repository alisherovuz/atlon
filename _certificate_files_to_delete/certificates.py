"""Certificate generation.

Produces an A4 landscape PDF awarded to people who bring others into the
community. Vector text, so it stays sharp when printed.

Fonts are bundled in fonts/ rather than taken from the system: Uzbek
names contain characters like oʻ and gʻ, and many names are written in
Cyrillic. ReportLab's built-in fonts cover neither and would silently
render them as blank boxes on the server.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime
from io import BytesIO

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

import config

logger = logging.getLogger("atlon-bot.certificates")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(BASE_DIR, "fonts")

# Same identity as the admin panel: indigo ground, Samarkand turquoise,
# saffron for the seal.
INK = HexColor("#10243B")
GLAZE = HexColor("#1B7F9E")
SAFFRON = HexColor("#E8A33D")
MUTED = HexColor("#4A5F78")
LINE = HexColor("#C7D2DE")

REGULAR, BOLD = "Atlon", "Atlon-Bold"
_fonts_ready = False


def _ensure_fonts() -> bool:
    """Register the bundled fonts once. Falls back to Helvetica if the
    files are missing, which keeps Latin names working."""
    global _fonts_ready, REGULAR, BOLD
    if _fonts_ready:
        return True
    try:
        pdfmetrics.registerFont(TTFont(REGULAR, os.path.join(FONT_DIR, "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont(BOLD, os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")))
        _fonts_ready = True
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Bundled fonts unavailable (%s); falling back to Helvetica. "
            "Cyrillic and oʻ/gʻ may not render.", exc
        )
        REGULAR, BOLD = "Helvetica", "Helvetica-Bold"
        _fonts_ready = True
    return True


def make_serial(user_id: int, issued: datetime | None = None) -> str:
    """Stable, unguessable-ish serial: AG-<year>-<6 hex>."""
    issued = issued or datetime.utcnow()
    digest = hashlib.sha256(
        f"{user_id}:{issued.date()}:{config.BOT_TOKEN[:8]}".encode()
    ).hexdigest()[:6].upper()
    return f"AG-{issued.year}-{digest}"


def _fit_font_size(text: str, font: str, max_width: float, start: int, floor: int = 20) -> int:
    """Largest size at which `text` fits on one line."""
    size = start
    while size > floor and pdfmetrics.stringWidth(text, font, size) > max_width:
        size -= 2
    return size


def render_certificate(
    name: str,
    invited_count: int,
    serial: str,
    issued: datetime | None = None,
) -> bytes:
    """Return the certificate as PDF bytes."""
    _ensure_fonts()
    issued = issued or datetime.utcnow()

    buf = BytesIO()
    W, H = landscape(A4)
    c = canvas.Canvas(buf, pagesize=(W, H))

    # ── frame ────────────────────────────────────────────────────
    c.setFillColor(HexColor("#FFFFFF"))
    c.rect(0, 0, W, H, stroke=0, fill=1)

    # Indigo band down the left edge, with a saffron hairline.
    c.setFillColor(INK)
    c.rect(0, 0, 26, H, stroke=0, fill=1)
    c.setFillColor(SAFFRON)
    c.rect(26, 0, 3, H, stroke=0, fill=1)

    # Thin rule framing the content area.
    c.setStrokeColor(LINE)
    c.setLineWidth(1)
    c.rect(58, 40, W - 100, H - 80, stroke=1, fill=0)

    cx = 29 + (W - 29) / 2  # centre of the area right of the band

    # ── wordmark ─────────────────────────────────────────────────
    c.setFont(BOLD, 19)
    c.setFillColor(INK)
    c.drawCentredString(cx, H - 92, "ATLON GROUP")
    c.setFont(REGULAR, 9)
    c.setFillColor(MUTED)
    c.drawCentredString(cx, H - 108, "Y O S H L A R   T A S H K I L O T I")

    # ── title ────────────────────────────────────────────────────
    c.setFont(BOLD, 40)
    c.setFillColor(GLAZE)
    c.drawCentredString(cx, H - 168, "SERTIFIKAT")

    c.setStrokeColor(SAFFRON)
    c.setLineWidth(2.5)
    c.line(cx - 46, H - 184, cx + 46, H - 184)

    c.setFont(REGULAR, 12.5)
    c.setFillColor(MUTED)
    c.drawCentredString(cx, H - 210, "Ushbu sertifikat quyidagi shaxsga taqdim etiladi")

    # ── recipient ────────────────────────────────────────────────
    max_w = W - 200
    size = _fit_font_size(name, BOLD, max_w, start=34)
    c.setFont(BOLD, size)
    c.setFillColor(INK)
    c.drawCentredString(cx, H - 258, name)

    c.setStrokeColor(LINE)
    c.setLineWidth(1)
    c.line(cx - 190, H - 272, cx + 190, H - 272)

    # ── reason ───────────────────────────────────────────────────
    reason = (
        f"Atlon Group hamjamiyatiga {invited_count} nafar ishtirokchini jalb "
        f"qilgani, faol ishtiroki va tashkilotimiz rivojiga qoʻshgan "
        f"hissasi uchun."
    )
    c.setFont(REGULAR, 12)
    c.setFillColor(MUTED)
    y = H - 302
    for line in simpleSplit(reason, REGULAR, 12, W - 260):
        c.drawCentredString(cx, y, line)
        y -= 17

    # ── seal ─────────────────────────────────────────────────────
    # Sits just under the citation rather than near the footer, so the
    # page reads as one block instead of two with a void between.
    seal_y = 196
    c.setStrokeColor(SAFFRON)
    c.setLineWidth(2)
    c.circle(cx, seal_y, 36, stroke=1, fill=0)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.8)
    c.circle(cx, seal_y, 41, stroke=1, fill=0)
    c.setFont(BOLD, 17)
    c.setFillColor(SAFFRON)
    c.drawCentredString(cx, seal_y + 3, "AG")
    c.setFont(REGULAR, 6.5)
    c.setFillColor(MUTED)
    c.drawCentredString(cx, seal_y - 14, "ATLON GROUP")

    # ── footer: date left, serial right ──────────────────────────
    c.setStrokeColor(LINE)
    c.setLineWidth(1)
    c.line(110, 96, 250, 96)
    c.line(W - 250, 96, W - 110, 96)

    c.setFont(REGULAR, 10)
    c.setFillColor(INK)
    c.drawCentredString(180, 80, issued.strftime("%d.%m.%Y"))
    c.setFont(REGULAR, 8)
    c.setFillColor(MUTED)
    c.drawCentredString(180, 66, "Berilgan sana")

    c.setFont(REGULAR, 10)
    c.setFillColor(INK)
    c.drawCentredString(W - 180, 80, serial)
    c.setFont(REGULAR, 8)
    c.setFillColor(MUTED)
    c.drawCentredString(W - 180, 66, "Sertifikat raqami")

    c.setTitle(f"Atlon Group sertifikati — {name}")
    c.setAuthor("Atlon Group")
    c.showPage()
    c.save()
    return buf.getvalue()
