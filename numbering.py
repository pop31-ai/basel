"""Сквозная нумерация документов и проводок с префиксами и постфиксами.

Формат номера: {prefix}{seq:0{pad}}{suffix}[#]{period}
Например: ПБ-000123/2026, АКТ-000015.
Счетчики хранятся в файле numbering.json; сквозная нумерация не сбрасывается
по периодам (сквозная), либо может быть привязана к периоду в настройке.
"""
from __future__ import annotations
from typing import Dict, Optional
from datetime import datetime, date
from .storage import Store


DEFAULT_FORMATS: Dict[str, Dict] = {
    "entry": dict(prefix="ПБ-", suffix="", pad=6, sep="/", period="year"),
    "act":   dict(prefix="АКТ-", suffix="", pad=5, sep="/", period=None),
    "inv":   dict(prefix="СЧ-", suffix="", pad=5, sep="/", period=None),
    "pay":   dict(prefix="ПКО-", suffix="", pad=5, sep="/", period=None),
}


class Numbering:
    """Сквозная нумерация. formats — схема для каждого типа документа."""

    def __init__(self, store: Store, formats: Optional[Dict[str, Dict]] = None):
        self.store = store
        self.formats = DEFAULT_FORMATS if formats is None else formats
        self._counters = self._load()

    def _load(self) -> Dict[str, Dict]:
        return self.store.read_json("numbering.json", {})

    def _save(self) -> None:
        self.store.write_json("numbering.json", self._counters)

    def configure(self, doc_type: str, prefix: str = None, suffix: str = None,
                  pad: int = None, period: Optional[str] = None) -> None:
        fmt = self.formats.setdefault(doc_type, {"prefix": "", "suffix": "", "pad": 6, "period": None})
        if prefix is not None:
            fmt["prefix"] = prefix
        if suffix is not None:
            fmt["suffix"] = suffix
        if pad is not None:
            fmt["pad"] = pad
        if "period" in {"period": period} or period is not None:
            fmt["period"] = period
        if not fmt.get("sep"):
            fmt["sep"] = "/"

    # ---- внутренние счетчики ----
    def _key(self, doc_type: str, d: date) -> str:
        fmt = self.formats.get(doc_type)
        period = fmt.get("period") if fmt else None
        if period == "year":
            return f"{doc_type}:{d.year}"
        if period == "month":
            return f"{doc_type}:{d.year}-{d.month:02d}"
        return f"{doc_type}:all"

    def set_format(self, doc_type: str, fmt: Dict) -> None:
        """Полная замена формата: {prefix, suffix, pad, period, sep}."""
        self.formats[doc_type] = dict(DEFAULT_FORMATS.get(doc_type, {}), **fmt)
        self._save()

    def next(self, doc_type: str, d: date = None) -> str:
        d = d or date.today()
        key = self._key(doc_type, d)
        ctr = self._counters.setdefault(key, {"n": 0, "last": None})
        ctr["n"] += 1
        n = ctr["n"]
        ctr["last"] = d.isoformat()
        fmt = self.formats[doc_type]
        seq = str(n).zfill(int(fmt.get("pad", 6)))
        base = {"year": d.year, "month": d.month, "day": d.day}
        prefix = str(fmt.get("prefix", "")).format_map(base)
        suffix = str(fmt.get("suffix", "")).format_map(base)
        sep = str(fmt.get("sep", ""))
        period = fmt.get("period")
        tail = ""
        if period == "year":
            tail = f"{sep}{d.year}"
        elif period == "month":
            tail = f"{sep}{d.year}-{d.month:02d}"
        self._save()
        return f"{prefix}{seq}{suffix}{tail}"