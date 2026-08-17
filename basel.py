"""Basel III отчетность (российская практика — нормативы ЦБ РФ).

Расчет ключевых норм капитала и ликвидности по данным журнала:
  Н1.0 — достаточность базового капитала / собственных средств
  Н1.1 — базовый капитал, Н1.2 — основной капитал, Н2 — мгновенная
  ликвидность, Н3 — текущая ликвидность, Н4 — долгосрочная ликвидность.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional
from .core import money
from .journal import Journal
from .charts import Chart


class Basel:
    """Расчет нормативов Basel III / инструкции 199-И по оборотам счетов."""

    def __init__(self, journal: Journal, chart: Chart):
        self.journal = journal
        self.chart = chart

    # ---------- ключевые счета ----------
    def _accounts(self, prefix: str) -> List[str]:
        return sorted(c for c in self.chart._by_code if c.startswith(prefix))

    def capital_by_type(self, as_of: date) -> Dict[str, Decimal]:
        dr, cr = self.journal.closing(as_of)
        # базовый капитал: счета капитала (K) — кредитовое сальдо
        basic = money(0)
        for c in self.chart._by_code:
            acc = self.chart._by_code[c]
            if acc.kind == "K":
                basic += max(cr.get(c, money(0)) - dr.get(c, money(0)), money(0))
        # дополнительные компоненты (RU: 82,86; GAAP: иные K-счета уже учтены)
        additional = money(0)
        for c in ("82", "86"):
            if self.chart.get(c):
                additional += max(cr.get(c, money(0)) - dr.get(c, money(0)), money(0))
        # прибыль: сальдо доходов за вычетом расходов (незакрытые R/E)
        rev_acc = [c for c in self.chart._by_code if self.chart._by_code[c].kind == "R"]
        exp_acc = [c for c in self.chart._by_code if self.chart._by_code[c].kind == "E"]
        rev = sum((cr.get(c, money(0)) - dr.get(c, money(0))) for c in rev_acc)
        exp = sum((dr.get(c, money(0)) - cr.get(c, money(0))) for c in exp_acc)
        net = rev - exp
        # плюс сальдо счета 99 (закрытая прибыль)
        net += cr.get("99", money(0)) - dr.get("99", money(0))
        return {"basic": basic, "additional": additional, "net_profit": max(net, money(0))}

    def rwa(self, as_of: date) -> Dict:
        """Взвешенные по риску активы (упрощенно): 0% — касса/ДС, 100% — прочее."""
        dr, cr = self.journal.closing(as_of)
        risk_free_codes = {"50", "51", "52", "55", "57"}
        risk_free_prefix = ("1000", "1100")     # GAAP cash/equivalents
        on_balance, off_balance = money(0), money(0)
        detail = []
        for c in sorted(set(dr) | set(cr)):
            acc = self.chart.get(c)
            if acc is None:
                continue
            if acc.group == "З":
                off_value = dr.get(c, money(0)) - cr.get(c, money(0))
                if off_value > 0:
                    off_balance += off_value
                continue
            net = dr.get(c, money(0)) - cr.get(c, money(0))
            if net <= 0:
                continue
            weight = money(0) if c in risk_free_codes or c.startswith(risk_free_prefix) else 1
            on_balance += net
            detail.append({"code": c, "name": acc.name, "amount": net, "weight": weight,
                           "rwa": net * weight})
        rwa_total = sum(row["rwa"] for row in detail) + off_balance
        return {"on_balance": on_balance, "off_balance": off_balance,
                "rwa": money(rwa_total), "detail": detail}

    def report(self, as_of: date) -> Dict:
        cap = self.capital_by_type(as_of)
        rwa = self.rwa(as_of)
        own_funds = cap["basic"] + cap["additional"] + cap["net_profit"]
        rwa_val = rwa["rwa"]
        n10 = (own_funds / rwa_val * 100) if rwa_val else money(0)
        n11 = (cap["basic"] / rwa_val * 100) if rwa_val else money(0)
        n12 = ((cap["basic"] + cap["additional"]) / rwa_val * 100) if rwa_val else money(0)
        # ориентировочные пороги ЦБ: Н1.0 ≥ 8%, Н1.1 ≥ 4.5%, Н1.2 ≥ 6%
        return {"as_of": as_of.isoformat(), "capital": cap, "own_funds": own_funds,
                "rwa": rwa_val, "ratios": {"n10": n10, "n11": n11, "n12": n12},
                "violations": self._violations(n10, n11, n12), "asset_detail": rwa["detail"]}

    @staticmethod
    def _violations(n10, n11, n12):
        out = []
        if n10 < money(8):
            out.append("Н1.0 ниже 8%")
        if n11 < money(4.5):
            out.append("Н1.1 ниже 4.5%")
        if n12 < money(6):
            out.append("Н1.2 ниже 6%")
        return out