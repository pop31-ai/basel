"""Шаблонные операции учета: добавление/удаление/применение."""
from __future__ import annotations
import json
from datetime import date
from decimal import Decimal
from typing import Dict, List
from .core import TemplateOp, Line, money
from .storage import Store


class Templates:
    """Каталог шаблонных операций (шаблоны: код, наименование, строки Дт/Кт с выражениями суммы)."""

    def __init__(self, store: Store):
        self.store = store
        self._items: Dict[str, TemplateOp] = {}
        self.reload()

    def reload(self) -> None:
        data = self.store.read_json("templates.json", {})
        self._items = {k: TemplateOp.from_dict(v) for k, v in data.items()}

    def _save(self) -> None:
        self.store.write_json("templates.json", {k: v.to_dict() for k, v in self._items.items()})

    # ---------- CRUD ----------
    def add(self, code: str, name: str, desc: str = "", lines: List[Dict] = None) -> TemplateOp:
        if code in self._items:
            raise ValueError(f"Шаблон {code} уже существует")
        op = TemplateOp(code=code, name=name, desc=desc, lines=lines or [])
        self._items[code] = op
        self._save()
        return op

    def remove(self, code: str) -> bool:
        if code not in self._items:
            return False
        del self._items[code]
        self._save()
        return True

    def get(self, code: str) -> TemplateOp:
        if code not in self._items:
            raise KeyError(f"Шаблон {code} не найден")
        return self._items[code]

    def list(self) -> List[TemplateOp]:
        return [self._items[k] for k in sorted(self._items)]

    # ---------- применение ----------
    def apply(self, code: str, params: Dict[str, str]) -> List[Line]:
        """Подставляет параметры {x} в суммы строк шаблона и возвращает строки проводки."""
        op = self.get(code)
        ctx = dict(params)
        ctx["rate_vat"] = ctx.get("rate_vat", "0.2")
        lines = []
        for ln in op.lines:
            amt = eval_amount(ln["amount"], ctx)
            analytics = {k: str(v) for k, v in ln.get("analytics", {}).items()}
            # в аналитике тоже можно подставлять {var}
            for k, v in list(analytics.items()):
                analytics[k] = substitute(v, ctx)
            lines.append(Line(debit=ln["debit"], credit=ln["credit"], amount=amt, analytics=analytics))
        return lines

    def to_seed(self) -> List[TemplateOp]:
        return self.list()


def substitute(s: str, ctx: Dict[str, str]) -> str:
    out = s
    for k, v in ctx.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def eval_amount(expr: str, ctx: Dict[str, str]) -> Decimal:
    """Вычисление суммы по выражению с параметрами, например '{sum}*0.2' и '{sum}/{1+0.2}'.

    Поддерживаются арифметика +,-,*,/ и скобки. Параметры — числа из ctx.
    """
    import re
    s = substitute(expr, ctx).replace(",", ".")
    # защита: допускаем только цифры, . + - * / ( ) пробелы
    if not re.fullmatch(r"[0-9.+\-*/( )]+", s):
        raise ValueError(f"Недопустимое выражение суммы: {expr}")
    safe = {"__builtins__": {}}
    return money(float(eval(s, safe, {}))) if s.strip() else money(0)


def default_templates() -> List[TemplateOp]:
    """Базовый набор типовых хозяйственных операций."""
    return [
        TemplateOp(code="sale", name="Реализация товара покупателю", desc="Дт 62 Кт 90.1 (выручка), Дт 90.3 Кт 68.НДС",
                   lines=[
                       {"debit": "62", "credit": "90", "amount": "{sum}", "analytics": {"buyer": "{buyer}"}},
                       {"debit": "90", "credit": "68", "amount": "{sum}*{rate_vat}/(1+{rate_vat})"},
                   ]),
        TemplateOp(code="receive_payment", name="Поступление оплаты от покупателя",
                   lines=[{"debit": "51", "credit": "62", "amount": "{sum}", "analytics": {"buyer": "{buyer}"}}]),
        TemplateOp(code="pay_supplier", name="Оплата поставщику",
                   lines=[{"debit": "60", "credit": "51", "amount": "{sum}", "analytics": {"supplier": "{supplier}"}}]),
        TemplateOp(code="buy", name="Закупка материалов у поставщика (без НДС)",
                   lines=[{"debit": "10", "credit": "60", "amount": "{sum}", "analytics": {"supplier": "{supplier}"}}]),
        TemplateOp(code="salary", name="Начисление заработной платы",
                   lines=[{"debit": "20", "credit": "70", "amount": "{sum}"}]),
        TemplateOp(code="cash_deposit", name="Взнос в кассу из банка",
                   lines=[{"debit": "50", "credit": "51", "amount": "{sum}"}]),
        TemplateOp(code="close_period", name="Закрытие финансового результата (прибыль)",
                   lines=[{"debit": "90", "credit": "99", "amount": "{sum}"}]),
    ]


def seed_templates(store: Store) -> None:
    t = Templates(store)
    if not t.list():
        for op in default_templates():
            t.add(op.code, op.name, op.desc, op.lines)
        print(f"Шаблоны операций созданы: {len(t.list())} шт.")