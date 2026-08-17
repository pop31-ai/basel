"""Типы данных: счета, аналитика, проводки, документы."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, List, Any

Q = Decimal("0.01")


def money(value) -> Decimal:
    """Приводим к Decimal с округлением до копеек."""
    return Decimal(str(value)).quantize(Q, rounding=ROUND_HALF_UP)


# Типы счетов (нормальная сторона):
# A - актив (Дт), P - пассив (Кт), K - капитал (Кт), R - доходы (Кт), E - расходы (Дт),
# Z - забалансовый счет.
SIDE = {"A": "D", "P": "C", "K": "C", "R": "C", "E": "D", "Z": None}


@dataclass
class Account:
    code: str
    name: str
    kind: str = "A"              # A/P/K/R/E/Z
    group: str = "Б"             # секция (I..VIII) или ЗАБ
    extra: Dict[str, str] = field(default_factory=dict)

    @property
    def side(self) -> Optional[str]:
        return SIDE.get(self.kind)


@dataclass
class Line:
    debit: str                    # код счета по дебету
    credit: str                   # код счета по кредиту
    amount: Decimal
    analytics: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"debit": self.debit, "credit": self.credit,
                "amount": str(self.amount), "analytics": self.analytics}


@dataclass
class Entry:
    """Бухгалтерская проводка (журнальная запись)."""
    no: str
    date: date
    ts: datetime                   # посекундный тс
    desc: str
    lines: List[Line]
    source: str = "manual"         # manual / template:<code>
    seq: int = 0                   # монотонная последовательность для порядка внутри секунды

    def to_dict(self) -> Dict[str, Any]:
        return {"no": self.no, "date": self.date.isoformat(),
                "ts": self.ts.strftime("%Y-%m-%d %H:%M:%S"),
                "desc": self.desc, "source": self.source, "seq": self.seq,
                "lines": [l.to_dict() for l in self.lines]}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Entry":
        am = money
        return Entry(
            no=d["no"], date=date.fromisoformat(d["date"]),
            ts=datetime.strptime(d["ts"], "%Y-%m-%d %H:%M:%S"),
            desc=d.get("desc", ""), source=d.get("source", "manual"),
            seq=int(d.get("seq", 0)),
            lines=[Line(l["debit"], l["credit"], am(l["amount"]), l.get("analytics", {}))
                   for l in d["lines"]],
        )


@dataclass
class TemplateOp:
    """Шаблонная операция учета."""
    code: str
    name: str
    desc: str = ""
    lines: List[Dict[str, Any]] = field(default_factory=list)   # debit/credit/amount(expr)/analytics(dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "name": self.name, "desc": self.desc, "lines": self.lines}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "TemplateOp":
        return TemplateOp(code=d["code"], name=d["name"], desc=d.get("desc", ""),
                          lines=d.get("lines", []))