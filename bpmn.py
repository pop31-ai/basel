"""Схемы проводок в нотации BPMN (SVG).

Схема операции — последовательность шагов (старт, задачи-проводки, шлюз, конец).
Каждая задача подписана проводкой: Дт X → Кт Y, сумма.
"""
from __future__ import annotations
from typing import List, Dict
from .core import TemplateOp


def _svg_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def render_bpmn(title: str, steps: List[Dict], width: int = 1200, height: int = 360) -> str:
    """steps: [{name, debit, credit, amount, detail}] -> SVG-схема BPMN."""
    n = len(steps)
    bw = 230
    gap = 70
    x0, y0 = 80, 180
    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
               f'viewBox="0 0 {width} {height}" font-family="DejaVu Sans, Arial, sans-serif">')
    svg.append(f'<rect x="10" y="10" width="{width-20}" height="{height-20}" rx="10" fill="#fbfbfb" '
               f'stroke="#bbb" stroke-width="1"/>')
    svg.append(f'<text x="{width/2}" y="44" text-anchor="middle" font-size="20" font-weight="bold" '
               f'fill="#222">{_svg_escape(title)}</text>')

    # стартовое событие
    cx = x0
    cy = y0
    svg.append(f'<circle cx="{cx}" cy="{cy}" r="22" fill="#fff" stroke="#111" stroke-width="2"/>')
    svg.append(f'<circle cx="{cx}" cy="{cy}" r="26" fill="none" stroke="#111" stroke-width="1.5"/>')
    svg.append(f'<text x="{cx}" y="{cy+4}" text-anchor="middle" font-size="13" fill="#111">С</text>')
    prev_x = cx + 30

    for i, st in enumerate(steps):
        x = prev_x + gap
        y = y0
        # стрелка
        svg.append(f'<line x1="{prev_x}" y1="{cy}" x2="{x}" y2="{cy}" stroke="#111" stroke-width="1.5" '
                   f'marker-end="url(#arr)"/>')
        # задача
        svg.append(f'<rect x="{x}" y="{y-60}" width="{bw}" height="{120}" rx="8" fill="#eef5ff" '
                   f'stroke="#2b6cb0" stroke-width="1.6"/>')
        svg.append(f'<text x="{x+bw/2}" y="{y-38}" text-anchor="middle" font-size="13" font-weight="bold" '
                   f'fill="#1a365d">{_svg_escape(st.get("name", f"Шаг {i+1}"))}</text>')
        svg.append(f'<text x="{x+bw/2}" y="{y-18}" text-anchor="middle" font-size="11" fill="#333">'
                   f'Дт {_svg_escape(st.get("debit", ""))} → Кт {_svg_escape(st.get("credit", ""))}</text>')
        svg.append(f'<text x="{x+bw/2}" y="{y+4}" text-anchor="middle" font-size="12" fill="#2b6cb0" '
                   f'font-weight="bold">{_svg_escape(st.get("amount", ""))}</text>')
        svg.append(f'<text x="{x+bw/2}" y="{y+24}" text-anchor="middle" font-size="10" fill="#666">'
                   f'{_svg_escape(st.get("detail", ""))}</text>')
        # шлюз (диамант) после каждой задачи кроме последней
        if i < n - 1:
            gx = x + bw + gap // 2 - 20
            gy = y0
            svg.append(f'<line x1="{x+bw}" y1="{cy}" x2="{gx}" y2="{cy}" stroke="#111" stroke-width="1.5" '
                       f'marker-end="url(#arr)"/>')
            svg.append(f'<polygon points="{gx},{gy-22} {gx+22},{gy} {gx},{gy+22} {gx-22},{gy}" '
                       f'fill="#fff8dc" stroke="#b7791f" stroke-width="1.5"/>')
            svg.append(f'<text x="{gx}" y="{gy+4}" text-anchor="middle" font-size="11" fill="#744210">'
                       f'{_svg_escape(st.get("gate", "контроль"))}</text>')
            prev_x = gx + 30
        else:
            prev_x = x + bw + 30

    # конечное событие
    ex = prev_x + gap
    svg.append(f'<line x1="{prev_x}" y1="{cy}" x2="{ex}" y2="{cy}" stroke="#111" stroke-width="1.5" '
               f'marker-end="url(#arr)"/>')
    svg.append(f'<circle cx="{ex}" cy="{cy}" r="24" fill="#fff" stroke="#111" stroke-width="2.5"/>')
    svg.append(f'<circle cx="{ex}" cy="{cy}" r="18" fill="#d4edda" stroke="#111" stroke-width="1.5"/>')
    svg.append(f'<text x="{ex}" y="{cy+4}" text-anchor="middle" font-size="13" fill="#111">К</text>')

    svg.append('<defs><marker id="arr" markerWidth="10" markerHeight="7" refX="9" refY="3.5" '
               'orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="#111"/></marker></defs>')
    svg.append('</svg>')
    return "\n".join(svg)


def scheme_from_template(tp: TemplateOp, params: Dict[str, str] = None) -> str:
    """Строит BPMN-схему из шаблона операции: каждая строка проводки — задача."""
    params = params or {}
    from .templates import substitute
    steps = []
    for i, ln in enumerate(tp.lines, 1):
        amount_expr = substitute(ln["amount"], params)
        an = ", ".join(f"{k}={substitute(v, params)}" for k, v in ln.get("analytics", {}).items())
        steps.append({
            "name": f"Шаг {i}",
            "debit": ln["debit"], "credit": ln["credit"],
            "amount": amount_expr, "detail": an or "проводка",
            "gate": "баланс",
        })
    title = f"{tp.code} — {tp.name}"
    return render_bpmn(title, steps)


def save_scheme_svg(content: str, path: str) -> None:
    from pathlib import Path
    Path(path).write_text(content, encoding="utf-8")