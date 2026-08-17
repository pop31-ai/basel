"""Отчеты: оборотно-сальдовая ведомость, бухгалтерский баланс, отчет о финансовых результатах."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Dict, List
from .core import money
from .journal import Journal
from .charts import Chart

SECTIONS = {name: i for i, name in enumerate(
    ["Внеоборотные активы", "Производственные запасы", "Затраты на производство",
     "Готовая продукция и товары", "Денежные средства", "Расчеты", "Капитал",
     "Финансовые результаты", "Забалансовые счета"])}


def _section_sort(rows: List[dict], chart: Chart) -> List[dict]:
    def key(r):
        c = chart.get(r["code"])
        if c is None:
            return 99
        g = c.group
        if g == "З":
            return 98
        try:
            return int(g[:1]) if g[:1].isdigit() else 0
        except (ValueError, IndexError):
            return 0
    return sorted(rows, key=key)


class Reports:
    def __init__(self, journal: Journal, chart: Chart):
        self.journal = journal
        self.chart = chart

    # ---------- ОСВ ----------
    def osv(self, d_from: date, d_to: date) -> List[dict]:
        rows = self.journal.osv(d_from, d_to)
        return [r for r in rows if self.chart.get(r["code"]) is not None and self.chart.get(r["code"]).group != "З"]

    # ---------- Баланс ----------
    def balance(self, as_of: date) -> Dict:
        close_dr, close_cr = self.journal.closing(as_of)
        assets, liabilities, equity = [], [], []
        codes = set(close_dr) | set(close_cr)
        profit = money(0)
        for c in sorted(codes):
            acc = self.chart.get(c)
            if acc is None or acc.group == "З":
                continue
            net = close_dr.get(c, money(0)) - close_cr.get(c, money(0))
            if net == 0:
                continue
            if acc.kind == "R":
                # доходы/расходы до закрытия периода: кредитовое сальдо = прибыль
                profit += max(-net, money(0))
            elif acc.kind == "K":
                # капитал — на пассивной стороне (норма: кредитовое сальдо)
                equity.append((c, acc.name, abs(net)))
            elif net > 0:
                # дебетовое сальдо -> актив (или обратное сальдо пассива)
                assets.append((c, acc.name, net))
            else:
                # кредитовое сальдо -> пассив (или обратное сальдо актива)
                liabilities.append((c, acc.name, -net))
        total_a = sum(x[2] for x in assets)
        total_l = sum(x[2] for x in liabilities) + sum(x[2] for x in equity) + profit
        return {"assets": assets, "liabilities": liabilities, "equity": equity,
                "profit": profit, "total_assets": total_a, "total_liab": total_l,
                "off_balance": self._off_balance(as_of)}

    def _off_balance(self, as_of: date) -> List[tuple]:
        close_dr, close_cr = self.journal.closing(as_of)
        out = []
        for c in sorted(set(close_dr) | set(close_cr)):
            acc = self.chart.get(c)
            if acc and acc.group == "З":
                out.append((c, acc.name, close_dr.get(c, 0) - close_cr.get(c, 0)))
        return out

    # ---------- ОФР ----------
    def income(self, d_from: date, d_to: date) -> Dict:
        dr, cr = self.journal.registers_period(d_from, d_to)
        revenue, expenses = money(0), money(0)
        detail_rev, detail_exp = {}, {}
        for c in sorted(set(dr) | set(cr)):
            acc = self.chart.get(c)
            if acc is None or acc.group == "З":
                continue
            delta = cr.get(c, money(0)) - dr.get(c, money(0))
            if acc.kind == "R":
                revenue += delta
                detail_rev[c] = delta
            elif acc.kind == "E":
                expenses += -delta
                detail_exp[c] = delta
        profit = revenue - expenses
        return {"revenue": revenue, "expenses": expenses, "profit": profit,
                "detail_rev": detail_rev, "detail_exp": detail_exp}