"""BI-модуль: агрегации по аналитике, динамика, топы, старение задолженности."""
from __future__ import annotations
import calendar
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List
from .core import money
from .journal import Journal
from .charts import Chart


def _month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def _month_after(d: date) -> date:
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


class BI:
    def __init__(self, journal: Journal, chart: Chart):
        self.journal = journal
        self.chart = chart

    def _lines(self, d_from: date, d_to: date):
        for e in self.journal.entries_in(d_from, d_to):
            for l in e.lines:
                yield e, l

    def _months(self, d_from: date, d_to: date) -> List[date]:
        out, cur = [], date(d_from.year, d_from.month, 1)
        while cur <= d_to:
            out.append(cur)
            cur = _month_after(cur)
        return out

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

    def counterparties(self, account: str, dimension: str, d_from: date, d_to: date,
                       n: int = 15) -> List[Dict]:
        """Топ контрагентов по счету (62 — покупатели, 60 — поставщики...)."""
        rows = self.pivot(dimension, d_from, d_to, account)
        return [{"key": r["key"], "debit": r["debit"], "credit": r["credit"], "net": r["net"]}
                for r in rows[:n]]

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

    def profit_monthly(self, d_from: date, d_to: date) -> List[Dict]:
        """Помесячно: выручка/расходы/прибыль по счетам 90/91/99 (ОФР)."""
        rows = []
        for m0 in self._months(d_from, d_to):
            m1 = min(_month_end(m0), d_to)
            rev, exp = money(0), money(0)
            for e in self.journal.entries_in(m0, m1):
                for l in e.lines:
                    if self.chart.get(l.debit) is None or self.chart.get(l.credit) is None:
                        continue
                    dacc, cacc = self.chart.get(l.debit), self.chart.get(l.credit)
                    if dacc.kind == "R":
                        rev -= l.amount
                    if cacc.kind == "R":
                        rev += l.amount
                    if dacc.kind == "E":
                        exp += l.amount
                    if cacc.kind == "E":
                        exp -= l.amount
            rows.append({"month": m0.strftime("%Y-%m"),
                         "revenue": rev, "expenses": exp, "profit": rev - exp})
        return rows

    def top_accounts(self, d_from: date, d_to: date, n: int = 10) -> List[Dict]:
        agg: Dict[str, Decimal] = {}
        for e, l in self._lines(d_from, d_to):
            for code in (l.debit, l.credit):
                acc = self.chart.get(code)
                name = acc.name if acc else code
                agg.setdefault(code, {"code": code, "name": name, "amount": money(0)})
                agg[code]["amount"] += l.amount
        return sorted(agg.values(), key=lambda r: r["amount"], reverse=True)[:n]

    def crosstab(self, dimension: str, d_from: date, d_to: date,
                 measure: str = "amount") -> List[Dict]:
        """Двумерный разрез: строки — значение аналитики, столбцы — месяцы."""
        months = [m.strftime("%Y-%m") for m in self._months(d_from, d_to)]
        agg: Dict[str, Dict] = {}
        for e, l in self._lines(d_from, d_to):
            key = l.analytics.get(dimension, "(без аналитики)")
            mkey = e.date.strftime("%Y-%m")
            row = agg.setdefault(key, {})
            for m in months:
                row.setdefault(m, money(0))
            if measure == "debit":
                row[mkey] = row.get(mkey, money(0)) + l.amount
            elif measure == "credit":
                row[mkey] = row.get(mkey, money(0)) - l.amount
            else:
                row[mkey] = row.get(mkey, money(0)) + l.amount
        out = []
        for key, cells in agg.items():
            row = {"key": key}
            row.update(cells)
            out.append(row)
        return sorted(out, key=lambda r: r.get(d_to.strftime("%Y-%m"), money(0)), reverse=True)

    def aging(self, accounts: List[str], as_of: date,
              dimension: str = "buyer") -> List[Dict]:
        """Старение задолженности: нетто-сальдо по контрагенту и срок (в днях/месяцах)."""
        regs = self.journal.closing(as_of)
        dr, cr = regs
        rows = []
        for code in accounts:
            acc = self.chart.get(code)
            name = acc.name if acc else code
            net = dr.get(code, money(0)) - cr.get(code, money(0))
            # дата последнего движения по счету
            last = None
            for e in self.journal.entries_in(date(1900, 1, 1), as_of):
                for l in e.lines:
                    if l.debit == code or l.credit == code:
                        if last is None or e.date > last:  # type: ignore[operator]
                            last = e.date
            days = (as_of - last).days if last else None
            rows.append({"account": code, "name": name, "balance": abs(net),
                         "type": "дебиторская" if net > 0 else "кредиторская",
                         "days": days, "age": f"{days} дн." if days is not None else "—"})
        return [r for r in rows if r["balance"] > 0]

    def kpi(self, d_from: date, d_to: date) -> Dict:
        """Ключевые показатели периода."""
        pm = self.profit_monthly(d_from, d_to)
        revenue = sum((r["revenue"] for r in pm), money(0))
        expenses = sum((r["expenses"] for r in pm), money(0))
        top = self.top_accounts(d_from, d_to, 5)
        return {"revenue": revenue, "expenses": expenses, "profit": revenue - expenses,
                "top_accounts": top}