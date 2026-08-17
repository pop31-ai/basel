"""BI-модуль: агрегации по аналитике, динамика по месяцам, топы."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Dict, List
from .core import money
from .journal import Journal
from .charts import Chart


class BI:
    def __init__(self, journal: Journal, chart: Chart):
        self.journal = journal
        self.chart = chart

    def _lines(self, d_from: date, d_to: date):
        for e in self.journal.entries_in(d_from, d_to):
            for l in e.lines:
                yield e, l

    def pivot(self, dimension: str, d_from: date, d_to: date,
              account: str = None) -> List[Dict]:
        """Разрез по аналитике: сумма дебета и кредита по каждой группе."""
        agg: Dict[str, Dict] = {}
        for e, l in self._lines(d_from, d_to):
            if account and l.debit != account and l.credit != account:
                continue
            key = l.analytics.get(dimension, "(без аналитики)")
            row = agg.setdefault(key, {"key": key, "debit": money(0), "credit": money(0), "net": money(0)})
            if account:
                if l.debit == account:
                    row["debit"] += l.amount
                if l.credit == account:
                    row["credit"] += l.amount
            else:
                row["debit"] += l.amount
                row["credit"] += l.amount
            row["net"] = row["debit"] - row["credit"]
        return sorted(agg.values(), key=lambda r: r["net"], reverse=True)

    def monthly(self, d_from: date, d_to: date) -> List[Dict]:
        """Помесячно: обороты Дт/Кт и сальдо финансового результата."""
        months: Dict[str, Dict] = {}
        for e in self.journal.entries_in(d_from, d_to):
            key = e.date.strftime("%Y-%m")
            m = months.setdefault(key, {"month": key, "debit": money(0), "credit": money(0)})
            for l in e.lines:
                m["debit"] += l.amount
                m["credit"] += l.amount
        return [months[k] for k in sorted(months)]

    def top_accounts(self, d_from: date, d_to: date, n: int = 10) -> List[Dict]:
        agg: Dict[str, Decimal] = {}
        for e, l in self._lines(d_from, d_to):
            for code in (l.debit, l.credit):
                acc = self.chart.get(code)
                name = acc.name if acc else code
                agg.setdefault(code, {"code": code, "name": name, "amount": money(0)})
                agg[code]["amount"] += l.amount
        return sorted(agg.values(), key=lambda r: r["amount"], reverse=True)[:n]