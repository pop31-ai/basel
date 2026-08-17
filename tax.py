"""Налоговая отчетность: расчет и формирование файлов для сдачи (коротко)."""
from __future__ import annotations
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List
from .core import money
from .journal import Journal
from .storage import Store


class Tax:
    """Расчет налогов коротко: НДС и налог на прибыль, формирование декларации-файла."""

    def __init__(self, store: Store, journal: Journal):
        self.store = store
        self.journal = journal

    def vat(self, d_from: date, d_to: date) -> Dict:
        """НДС: начислено (68/90.03), вычет (19), к уплате."""
        dr, cr = self.journal.registers_period(d_from, d_to)
        accrued = cr.get("68", money(0))
        deductible = dr.get("19", money(0))
        payable = accrued - deductible
        return {"period": [d_from.isoformat(), d_to.isoformat()], "type": "VAT",
                "accrued": accrued, "deductible": deductible, "payable": payable,
                "date": date.today().isoformat()}

    def profit(self, d_from: date, d_to: date, rate: str = "0.20") -> Dict:
        """Налог на прибыль: (доходы - расходы) * ставка (упрощенно)."""
        dr, cr = self.journal.registers_period(d_from, d_to)
        income = cr.get("90", money(0)) + cr.get("91", money(0))
        vat_accrued = cr.get("68", money(0))
        costs = dr.get("90", money(0)) + dr.get("91", money(0)) - vat_accrued + dr.get("26", money(0)) + dr.get("44", money(0))
        base = income - costs
        tax = base * Decimal(rate)
        return {"period": [d_from.isoformat(), d_to.isoformat()], "type": "PROFIT",
                "income": income, "costs": costs, "base": base,
                "rate": rate, "tax": money(tax), "date": date.today().isoformat()}

    def submit(self, report: Dict) -> Dict:
        """Сдача отчетности: сохраняем файл декларации + отметка о приеме."""
        filename = f"decl_{report['type'].lower()}_{report['period'][0]}_{report['period'][1]}.json"
        p = self.store.write_json(f"tax/{filename}", report)
        accept = {"no": f"ACCEPT-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                  "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                  "status": "принято", "file": filename.strip("/")}
        ack_path = self.store.write_json(f"tax/{accept['no']}.json", accept)
        return {"report": report, "acceptance": accept, "file": str(p),
                "ack_file": str(ack_path)}