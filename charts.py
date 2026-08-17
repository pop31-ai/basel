"""Системы счетов.

Встроенные системы счетов:
  * ru      — План счетов РФ (Приказ 94н) — государственная система
  * us      — упрощенная система по GAAP-логике
  * ifrs    — упрощенная система по МСФО-логике
Систему также можно загрузить из файлов (json/csv).
"""
from __future__ import annotations
import csv, io, json
from pathlib import Path
from typing import List, Dict, Optional
from .core import Account


# План счетов РФ (Приказ Минфина 94н) — сводный список основных счетов.
RU_CHART: List[Dict] = [
    # I. Внеоборотные активы
    dict(code="01", name="Основные средства",            kind="A"),
    dict(code="02", name="Амортизация основных средств",  kind="P"),
    dict(code="03", name="Доходные вложения в материальные ценности", kind="A"),
    dict(code="04", name="Нематериальные активы",         kind="A"),
    dict(code="05", name="Амортизация нематериальных активов", kind="P"),
    dict(code="07", name="Оборудование к установке",      kind="A"),
    dict(code="08", name="Вложения во внеоборотные активы", kind="A"),
    dict(code="09", name="Отложенные налоговые активы",   kind="A"),
    dict(code="001", name="Арендованные основные средства", kind="Z", group="З"),
    dict(code="011", name="Основные средства, сданные в аренду", kind="Z", group="З"),
    # II. Производственные запасы
    dict(code="10", name="Материалы",                     kind="A"),
    dict(code="11", name="Животные на выращивании и откорме", kind="A"),
    dict(code="14", name="Резервы под снижение стоимости материальных ценностей", kind="P"),
    dict(code="15", name="Заготовление и приобретение материальных ценностей", kind="A"),
    dict(code="16", name="Отклонение в стоимости материальных ценностей", kind="A"),
    dict(code="19", name="НДС по приобретенным ценностям", kind="A"),
    dict(code="002", name="ТМЦ, принятые на ответственное хранение", kind="Z", group="З"),
    dict(code="003", name="Материалы, принятые в переработку", kind="Z", group="З"),
    dict(code="004", name="Товары, принятые на комиссию",  kind="Z", group="З"),
    dict(code="005", name="Оборудование, принятое для монтажа", kind="Z", group="З"),
    dict(code="006", name="Бланки строгой отчетности",    kind="Z", group="З"),
    # III. Затраты на производство
    dict(code="20", name="Основное производство",         kind="A"),
    dict(code="21", name="Полуфабрикаты собственного производства", kind="A"),
    dict(code="23", name="Вспомогательные производства",   kind="A"),
    dict(code="25", name="Общепроизводственные расходы",   kind="A"),
    dict(code="26", name="Общехозяйственные расходы",      kind="A"),
    dict(code="28", name="Брак в производстве",            kind="A"),
    dict(code="29", name="Обслуживающие производства и хозяйства", kind="A"),
    # IV. Готовая продукция и товары
    dict(code="40", name="Выпуск продукции",              kind="A"),
    dict(code="41", name="Товары",                         kind="A"),
    dict(code="42", name="Торговая наценка",               kind="P"),
    dict(code="43", name="Готовая продукция",              kind="A"),
    dict(code="44", name="Расходы на продажу",             kind="A"),
    dict(code="45", name="Товары отгруженные",             kind="A"),
    dict(code="46", name="Выполненные этапы по незавершенным работам", kind="A"),
    # V. Денежные средства
    dict(code="50", name="Касса",                          kind="A"),
    dict(code="51", name="Расчетные счета",                kind="A"),
    dict(code="52", name="Валютные счета",                 kind="A"),
    dict(code="55", name="Специальные счета в банках",     kind="A"),
    dict(code="57", name="Переводы в пути",                kind="A"),
    dict(code="58", name="Финансовые вложения",            kind="A"),
    dict(code="59", name="Резервы под обесценение финансовых вложений", kind="P"),
    dict(code="007", name="Списанная в убыток задолженность неплатежеспособных дебиторов", kind="Z", group="З"),
    dict(code="008", name="Обеспечения обязательств и платежей полученные", kind="Z", group="З"),
    dict(code="009", name="Обеспечения обязательств и платежей выданные", kind="Z", group="З"),
    # VI. Расчеты
    dict(code="60", name="Расчеты с поставщиками и подрядчиками", kind="P"),
    dict(code="62", name="Расчеты с покупателями и заказчиками", kind="A"),
    dict(code="63", name="Резервы по сомнительным долгам", kind="P"),
    dict(code="66", name="Расчеты по краткосрочным кредитам и займам", kind="P"),
    dict(code="67", name="Расчеты по долгосрочным кредитам и займам", kind="P"),
    dict(code="68", name="Расчеты по налогам и сборам",    kind="P"),
    dict(code="69", name="Расчеты по социальному страхованию и обеспечению", kind="P"),
    dict(code="70", name="Расчеты с персоналом по оплате труда", kind="P"),
    dict(code="71", name="Расчеты с подотчетными лицами",  kind="A"),
    dict(code="73", name="Расчеты с персоналом по прочим операциям", kind="A"),
    dict(code="75", name="Расчеты с учредителями",         kind="P"),
    dict(code="76", name="Расчеты с разными дебиторами и кредиторами", kind="P"),
    dict(code="77", name="Отложенные налоговые обязательства", kind="P"),
    dict(code="79", name="Внутрихозяйственные расчеты",    kind="A"),
    dict(code="010", name="Основные средства в аренде",    kind="Z", group="З"),
    # VII. Капитал
    dict(code="80", name="Уставный капитал",               kind="K"),
    dict(code="81", name="Собственные акции (доли)",       kind="K"),
    dict(code="82", name="Резервный капитал",              kind="K"),
    dict(code="83", name="Добавочный капитал",             kind="K"),
    dict(code="84", name="Нераспределенная прибыль (непокрытый убыток)", kind="K"),
    dict(code="86", name="Целевое финансирование",         kind="K"),
    # VIII. Финансовые результаты
    dict(code="90", name="Продажи",                        kind="R"),
    dict(code="91", name="Прочие доходы и расходы",        kind="R"),
    dict(code="94", name="Недостачи и потери от порчи ценностей", kind="E"),
    dict(code="96", name="Резервы предстоящих расходов",   kind="P"),
    dict(code="97", name="Расходы будущих периодов",       kind="A"),
    dict(code="98", name="Доходы будущих периодов",        kind="P"),
    dict(code="99", name="Прибыли и убытки",               kind="P"),
    # субсчета (типовые)
    dict(code="60.01", name="Расчеты с поставщиками и подрядчиками", kind="P"),
    dict(code="60.02", name="Авансы выданные",               kind="A"),
    dict(code="62.01", name="Расчеты с покупателями и заказчиками", kind="A"),
    dict(code="62.02", name="Авансы полученные",             kind="P"),
    dict(code="68.02", name="Расчеты по НДС",                kind="P"),
    dict(code="68.04", name="Расчеты по налогу на прибыль",  kind="P"),
    dict(code="69.01", name="Взносы в ФСС",                  kind="P"),
    dict(code="69.02", name="Взносы в ПФР",                  kind="P"),
    dict(code="69.03", name="Взносы в ФФОМС",                kind="P"),
    dict(code="90.1",  name="Выручка",                       kind="R"),
    dict(code="90.2",  name="Себестоимость продаж",          kind="E"),
    dict(code="90.3",  name="НДС с продаж",                  kind="E"),
    dict(code="90.9",  name="Прибыль/убыток от продаж",      kind="E"),
    dict(code="91.1",  name="Прочие доходы",                 kind="R"),
    dict(code="91.2",  name="Прочие расходы",                kind="E"),
    dict(code="91.9",  name="Сальдо прочих доходов/расходов", kind="E"),
]


class Chart:
    def __init__(self, accounts: List[Account], system: str = "ru", meta: Dict = None):
        self.system = system
        self.meta = meta or {}
        self.accounts = accounts
        self._by_code = {a.code: a for a in accounts}

    def get(self, code: str) -> Optional[Account]:
        return self._by_code.get(code)

    @property
    def free_form(self) -> bool:
        """True — система без фиксированного плана счетов (счета создаются на лету)."""
        return bool(self.meta.get("free_form"))

    def __getitem__(self, code: str) -> Account:
        a = self._by_code.get(code)
        if a is None:
            raise KeyError(f"Счет {code} отсутствует в системе счетов")
        return a

    def all(self) -> List[Account]:
        return self.accounts

    def to_dict(self) -> Dict:
        return {"system": self.system, "meta": self.meta,
                "accounts": [a.__dict__ | {"kind": a.kind} for a in self.accounts]}

    @staticmethod
    def from_dict(d: Dict) -> "Chart":
        return Chart(accounts=[Account(**{**a, "extra": a.get("extra", {})}) for a in d["accounts"]],
                     system=d.get("system", "custom"), meta=d.get("meta", {}))

    def save(self, path: str) -> None:
        if str(path).lower().endswith(".csv"):
            Path(path).write_text(self.to_csv(), encoding="utf-8")
        else:
            Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def to_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["code", "name", "kind", "group"])
        for a in self.accounts:
            w.writerow([a.code, a.name, a.kind, a.group])
        return buf.getvalue()


def builtin(system: str = "ru") -> Chart:
    if system == "ru":
        return Chart([Account(**a) for a in RU_CHART], system="ru",
                     meta={"name": "План счетов РФ (Приказ Минфина № 94н)", "state": True})
    if system == "us":
        return Chart([Account(**a) for a in US_CHART], system="us",
                     meta={"name": "Упрощенная система счетов (US-логика)"})
    if system == "ifrs":
        return Chart([Account(**a) for a in IFRS_CHART], system="ifrs",
                     meta={"name": "Упрощенная система счетов (МСФО)"})
    if system == "gaap":
        return Chart([], system="gaap",
                     meta={"name": "US GAAP — без фиксированного плана счетов "
                                    "(счета создаются автоматически)", "free_form": True})
    raise ValueError(f"Неизвестная система счетов: {system}")


# Simple US-style chart
US_CHART: List[Dict] = [
    dict(code="1000", name="Cash",                         kind="A", group="Assets"),
    dict(code="1100", name="Accounts receivable",         kind="A", group="Assets"),
    dict(code="1200", name="Inventory",                   kind="A", group="Assets"),
    dict(code="1300", name="Property and equipment",      kind="A", group="Assets"),
    dict(code="1400", name="Intangibles",                 kind="A", group="Assets"),
    dict(code="9000", name="Off-balance",                 kind="Z", group="Off"),
    dict(code="2000", name="Accounts payable",            kind="P", group="Liabilities"),
    dict(code="2100", name="Accrued liabilities",         kind="P", group="Liabilities"),
    dict(code="2200", name="Loans payable",               kind="P", group="Liabilities"),
    dict(code="2300", name="Taxes payable",               kind="P", group="Liabilities"),
    dict(code="2500", name="Deferred revenue",            kind="P", group="Liabilities"),
    dict(code="3000", name="Common stock",                kind="K", group="Equity"),
    dict(code="3100", name="Retained earnings",           kind="K", group="Equity"),
    dict(code="4000", name="Sales revenue",               kind="R", group="Revenue"),
    dict(code="4100", name="Service revenue",             kind="R", group="Revenue"),
    dict(code="5000", name="Cost of goods sold",          kind="E", group="Expense"),
    dict(code="5100", name="Operating expenses",          kind="E", group="Expense"),
    dict(code="5200", name="Tax expense",                 kind="E", group="Expense"),
]

# Simple IFRS-style chart
IFRS_CHART: List[Dict] = [
    dict(code="1000", name="Денежные средства",           kind="A", group="Активы"),
    dict(code="1100", name="Торговая дебиторская задолженность", kind="A", group="Активы"),
    dict(code="1200", name="Запасы",                       kind="A", group="Активы"),
    dict(code="1300", name="Основные средства",            kind="A", group="Активы"),
    dict(code="9000", name="Забалансовые",                 kind="Z", group="Забаланс"),
    dict(code="2000", name="Торговая кредиторская задолженность", kind="P", group="Обязательства"),
    dict(code="2100", name="Кредиты и займы",              kind="P", group="Обязательства"),
    dict(code="2200", name="Налоговые обязательства",      kind="P", group="Обязательства"),
    dict(code="3000", name="Акционерный капитал",          kind="K", group="Капитал"),
    dict(code="3100", name="Нераспределенная прибыль",     kind="K", group="Капитал"),
    dict(code="4000", name="Выручка",                      kind="R", group="Доходы"),
    dict(code="5000", name="Себестоимость",                kind="E", group="Расходы"),
    dict(code="5100", name="Административные расходы",     kind="E", group="Расходы"),
    dict(code="5200", name="Налоги на прибыль",            kind="E", group="Расходы"),
]


def load_file(path: str) -> Chart:
    """Загрузка системы счетов из файла: .json (объект Chart) или .csv (колонки code,name,kind,group)."""
    p = Path(path)
    if p.suffix.lower() == ".json":
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, dict) and "accounts" in d:
            return Chart.from_dict(d)
        return Chart([Account(**a) for a in d], system=p.stem)
    if p.suffix.lower() == ".csv":
        rows = csv.DictReader(p.open("r", encoding="utf-8-sig"))
        accounts = [Account(code=r["code"], name=r["name"],
                            kind=r.get("kind", "A"), group=r.get("group", "Б")) for r in rows]
        return Chart(accounts, system=p.stem)
    raise ValueError("Поддерживаются только .json и .csv")