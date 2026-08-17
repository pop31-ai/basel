"""Печать документов и отчетов в PDF и изображения (PNG).

Документы: счета (inv), акты (act), платежки (pay).
Отчеты: ОСВ, баланс, ОФР, BI-витрина.
"""
from __future__ import annotations
import io
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    _REPORTLAB = True
except Exception:                                  # pragma: no cover
    _REPORTLAB = False

FA, FB, FSI, FSB = "DejaVuSans", "DejaVuSans-Bold", "DejaVuSans-Oblique", "DejaVuSans-BoldOblique"


def _register_fonts():
    """Регистрация шрифтов reportlab (кириллица). Использует DejaVu или Arial Windows."""
    if not _REPORTLAB:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import glob, os
    mapping = {FA: "DejaVuSans.ttf", FB: "DejaVuSans-Bold.ttf",
               FSI: "DejaVuSans-Oblique.ttf", FSB: "DejaVuSans-BoldOblique.ttf"}
    # поиск по распространенным путям
    pools = [glob.glob(r"C:\Windows\Fonts\*.ttf"),
             glob.glob("/usr/share/fonts/truetype/dejavu/*.ttf"),
             glob.glob("/usr/share/fonts/truetype/msttcorefonts/*.ttf")]
    available = {}
    for grp in pools:
        for p in grp:
            base = os.path.basename(p)
            if base in mapping.values():
                available.setdefault(base, p)
    registered = pdfmetrics.getRegisteredFontNames()
    for reg, fname in mapping.items():
        if reg in registered:
            continue
        path = available.get(fname) or _windows_font()
        if not path:
            continue
        pdfmetrics.registerFont(TTFont(reg, path))


def _windows_font():
    import os
    for p in (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\DejaVuSans.ttf"):
        if os.path.exists(p):
            return p
    return None


class Renderer:
    """Единая отрисовка таблицы/текста в PDF-байты и PNG (Pillow)."""

    def __init__(self, title: str = "", subtitle: str = "", cols: List[str] = None,
                 rows: List[List] = None, foot: List[str] = None, col_widths: List[float] = None,
                 page_w: float = A4[0], page_h: float = A4[1], meta: Dict = None):
        self.title, self.subtitle = title, subtitle
        self.cols = cols or []
        self.rows = rows or []
        self.foot = foot or []
        self.col_widths = col_widths  # в точках
        self.page_w, self.page_h = page_w, page_h
        self.meta = meta or {}

    # ---------- PDF ----------
    def to_pdf(self) -> bytes:
        if not _REPORTLAB:
            raise RuntimeError("reportlab не установлен")
        _register_fonts()
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(self.page_w, self.page_h))
        c.setTitle(self.title)
        y = self.page_h - 40
        if self.subtitle:
            c.setFont(FA, 9); c.drawString(40, y, self.subtitle); y -= 16
        c.setFont(FB, 14); c.drawString(40, y, self.title); y -= 24
        if self.meta:
            c.setFont(FA, 8)
            for k, v in self.meta.items():
                c.drawString(40, y, f"{k}: {v}"); y -= 11
            y -= 6
        c.setStrokeColorRGB(0.25, 0.25, 0.25); c.setLineWidth(0.6)
        # заголовок колонок
        if self.cols:
            c.setFont(FSB, 9)
            x = 40
            for i, col in enumerate(self.cols):
                w = self._cw(i)
                c.drawString(x + 3, y, col[: min(len(col), int(w / 4.5))])
                c.setFont(FSB, 9)
                c.line(x, y - 3, x + w, y - 3)
                x += w
            c.line(40, y - 3, 40 + sum(self._widths()), y - 3)
            y -= 18
        c.setFont(FA, 8.5)
        for r_i, row in enumerate(self.rows):
            if y < 40:
                c.showPage(); _register_fonts()
                y = self.page_h - 40
                c.setFont(FA, 8.5)
            x = 40
            for i, cell in enumerate(row):
                txt = str(cell)
                c.drawString(x + 3, y, txt[: min(len(txt), int(self._cw(i) / 4.4))])
                x += self._cw(i)
            # сетка
            c.setLineWidth(0.3)
            c.setStrokeColorRGB(0.6, 0.6, 0.6)
            c.line(40, y - 3, 40 + sum(self._widths()), y - 3)
            y -= 15
        # нижние итоги
        if self.foot:
            y -= 6
            c.setFont(FSB, 9)
            for line in self.foot:
                c.drawString(40, y, line); y -= 13
        c.showPage()
        c.save()
        return buf.getvalue()

    def _cw(self, i: int) -> float:
        if self.col_widths and i < len(self.col_widths):
            return self.col_widths[i]
        return (self.page_w - 80) / max(len(self.cols), 1)

    def _widths(self) -> List[float]:
        return [self._cw(i) for i in range(len(self.cols or []))]

    # ---------- PNG (Pillow) ----------
    def to_png(self, scale: float = 1.4) -> bytes:
        from PIL import Image, ImageDraw, ImageFont
        pad = 20
        cw = [int(w * scale) for w in self._widths()] or [int((self.page_w - 120)) * scale]
        line_h = 16 * scale
        header_h = 70 * scale + (len(self.meta) * 12 * scale if self.meta else 0)
        foot_h = 40 * scale
        total_w = int(sum(cw) + pad * 2)
        total_h = int(header_h + line_h * (1 + len(self.rows)) + foot_h)
        img = Image.new("RGB", (total_w, total_h), "white")
        d = ImageDraw.Draw(img)
        f_title = self._font(18 * scale, bold=True)
        f_sub = self._font(11 * scale)
        f_head = self._font(11 * scale, bold=True)
        f_cell = self._font(10 * scale)
        f_foot = self._font(11 * scale, bold=True)
        y = int(pad * 0.7)
        if self.subtitle:
            d.text((pad, y), self.subtitle, fill="#444444", font=f_sub); y += 14 * scale
        d.text((pad, y), self.title, fill="#000000", font=f_title); y += 24 * scale
        for k, v in self.meta.items():
            d.text((pad, y), f"{k}: {v}", fill="#555555", font=f_sub); y += 12 * scale
        y += 6 * scale
        x = pad
        for i, col in enumerate(self.cols):
            d.rectangle([x, y, x + cw[i], y + line_h], outline="#333333", fill="#eaeaea")
            d.text((x + 4, y + 3), col, fill="#000000", font=f_head)
            x += cw[i]
        y += line_h
        for r_i, row in enumerate(self.rows):
            fill = "#ffffff" if r_i % 2 == 0 else "#f7f7f7"
            x = pad
            for i, cell in enumerate(row):
                d.rectangle([x, y, x + cw[i], y + line_h], outline="#999999", fill=fill)
                d.text((x + 4, y + 3), str(cell), fill="#111111", font=f_cell)
                x += cw[i]
            y += line_h
        if self.foot:
            y += 4 * scale
            for line in self.foot:
                d.text((pad, y), line, fill="#000000", font=f_foot); y += 14 * scale
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()

    def _font(self, size: int, bold: bool = False):
        from PIL import ImageFont
        for name in ("DejaVuSans-Bold" if bold else "DejaVuSans",
                     "arialbd" if bold else "arial",
                     "DejaVuSans", "Arial"):
            if "arial" in name.lower():
                candidates = [r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf"]
            else:
                candidates = [rf"C:\Windows\Fonts\{name}.ttf"]
            for p in candidates:
                try:
                    return ImageFont.truetype(p, size=size)
                except Exception:
                    continue
        return ImageFont.load_default()


def fmt_amount(v) -> str:
    """Денежное форматирование: 1 234 567,89"""
    s = format(abs(v), ",.2f").replace(",", " ").replace(".00", "")
    return ("− " if v < 0 else "") + s


def render_report(kind: str, filename: str, renderer: Renderer, store) -> Dict[str, Path]:
    """Сохраняет отчет и в PDF, и в PNG."""
    pdf = store.save_doc(kind, filename + ".pdf", renderer.to_pdf())
    png = store.save_doc(kind, filename + ".png", renderer.to_png())
    return {"pdf": pdf, "png": png}