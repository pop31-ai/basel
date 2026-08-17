"""Журнал операций: двойная запись (Дт/Кт), остатки, посекундный учет."""
from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from .core import Entry, Line, money
from .charts import Chart
from .storage import Store


def _gaap_kind(code: str) -> str:
    """Определяет тип счета по префиксу кода (US GAAP нумерация):
    1xx — активы, 2xx — пассивы, 3xx — капитал, 4xx — доходы, 5xx-6xx — расходы, 9xx — забалансовые."""
    digits = "".join(ch for ch in code if ch.isdigit())
    if not digits:
        return "A"
    ch = digits[0]
    if ch == "1":
        return "A"
    if ch == "2":
        return "P"
    if ch == "3":
        return "K"
    if ch == "4":
        return "R"
    if ch in "56":
        return "E"
    if ch == "9":
        return "Z"
    return "A"


class Journal:
    """Копит проводки в append-only файле journal.jsonl."""

    def __init__(self, store: Store, chart: Chart):
        self.store = store
        self.chart = chart

    # ---------- запись проводки ----------
    def post(self, date_: date, lines: List[Line], desc: str = "",
             no: Optional[str] = None, source: str = "manual", ts: Optional[datetime] = None) -> Entry:
        self._validate(lines)
        ts = ts or datetime.now().replace(microsecond=0)
        seq = self._next_seq(ts)
        entry = Entry(no=no or "", date=date_, ts=ts, desc=desc, lines=lines, source=source, seq=seq)
        # deferred numbering handled by caller (needs persistent counter) -> fill after
        self.store.append_entry(entry.to_dict())
        return entry

    def _next_seq(self, ts: datetime) -> int:
        """Порядковый номер проводки в текущем дне (для посекундного учета)."""
        day0 = ts.replace(hour=0, minute=0, second=0)
        cnt = 0
        for e in self._load_entries():
            t = datetime.strptime(e["ts"], "%Y-%m-%d %H:%M:%S")
            if t >= day0:
                cnt += 1
        return cnt

    def _validate(self, lines: List[Line]) -> None:
        if not lines:
            raise ValueError("Проводка не содержит строк")
        if not all(l.amount > 0 for l in lines):
            raise ValueError("Суммы строк должны быть положительными")
        for l in lines:
            if not self.chart.get(l.debit):
                if self.chart.free_form:
                    self._auto_add_account(l.debit)
                else:
                    raise ValueError(f"Счет {l.debit} не найден в системе счетов")
            if not self.chart.get(l.credit):
                if self.chart.free_form:
                    self._auto_add_account(l.credit)
                else:
                    raise ValueError(f"Счет {l.credit} не найден в системе счетов")

    def _auto_add_account(self, code: str) -> None:
        """GAAP: создает счет автоматически (тип по префиксу кода)."""
        from .core import Account
        kind = _gaap_kind(code)
        name = f"GAAP {code}"
        acc = Account(code=code, name=name, kind=kind, group="Свободные")
        self.chart.accounts.append(acc)
        self.chart._by_code[code] = acc
        self.store.write_json("chart.json", self.chart.to_dict())

    # ---------- чтение ----------
    def _load_entries(self) -> List[dict]:
        return self.store.read_entries()

    def entries(self) -> List[Entry]:
        return [Entry.from_dict(d) for d in self._load_entries()]

    def entries_in(self, d_from: date, d_to: date) -> List[Entry]:
        return [e for e in self.entries() if d_from <= e.date <= d_to]

    # ---------- остатки и обороты ----------
    @staticmethod
    def _registers(entries: List[Entry]) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
        """Вернет (dr_total, cr_total) по каждому счету."""
        dr: Dict[str, Decimal] = {}
        cr: Dict[str, Decimal] = {}
        for e in entries:
            for l in e.lines:
                dr[l.debit] = dr.get(l.debit, money(0)) + l.amount
                cr[l.credit] = cr.get(l.credit, money(0)) + l.amount
        return dr, cr

    def registers_period(self, d_from: date, d_to: date):
        return self._registers(self.entries_in(d_from, d_to))

    def opening(self, on_date: date):
        """Остатки на начало (до даты включительно накануне)."""
        prev = [e for e in self.entries() if e.date < on_date]
        return self._registers(prev)

    def closing(self, on_date: date):
        return self._registers([e for e in self.entries() if e.date <= on_date])

    def osv(self, d_from: date, d_to: date):
        """Оборотно-сальдовая ведомость.

        Возвращает список: (account, open_dr, open_cr, turn_dr, turn_cr, close_dr, close_cr)
        """
        op_dr, op_cr = self.opening(d_from)
        cur_dr, cur_cr = self._registers(self.entries_in(d_from, d_to))
        close_dr = {k: op_dr.get(k, money(0)) + cur_dr.get(k, money(0)) for k in set(op_dr) | set(cur_dr)}
        close_cr = {k: op_cr.get(k, money(0)) + cur_cr.get(k, money(0)) for k in set(op_cr) | set(cur_cr)}
        codes = sorted(set(op_dr) | set(op_cr) | set(cur_dr) | set(cur_cr))
        rows = []
        for c in codes:
            acc = self.chart.get(c)
            rows.append(dict(code=c, name=acc.name if acc else "?", group=acc.group if acc else "",
                             kind=acc.kind if acc else "",
                             open_dr=op_dr.get(c, money(0)), open_cr=op_cr.get(c, money(0)),
                             turn_dr=cur_dr.get(c, money(0)), turn_cr=cur_cr.get(c, money(0)),
                             close_dr=close_dr.get(c, money(0)), close_cr=close_cr.get(c, money(0))))
        return rows