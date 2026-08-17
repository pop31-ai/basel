"""Тестовые данные, комплекс загрузки и проверки (QA).

Генерация тестовых данных:
  * сценарий «закрытый год» — реалистичный оборот, гарантированно сходящийся
  * случайные проводки (детерминированный seed)
  * внешние файлы для ETL (банковская выписка CSV, счета JSON)

Комплекс загрузки (LoadComplex) исполняет план из шагов:
  chart -> templates -> scenario -> etl -> manual

Проверки (Checks) оценивают корректность данных:
  баланс проводки, обороты ОСВ, баланс (актив=пассив), существование счетов,
  положительные суммы, дедупликация, рендер отчетов, Basel.
"""
from __future__ import annotations
import json, random
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from .core import Line, money
from .charts import Chart, builtin, load_file
from .storage import Store
from .journal import Journal
from .numbering import Numbering
from .templates import Templates, seed_templates
from .reports import Reports
from .bi import BI
from .tax import Tax
from .basel import Basel


# ============================================================
# Генератор тестовых данных
# ============================================================
class TestData:
    """Генерация тестовых данных (детерминированная)."""

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)

    # ---------- закрытый сценарий (год, все сходится) ----------
    def closed_year(self) -> List[dict]:
        """Полный хозяйственный цикл: УК, закупка, продажа, НДС, зарплата,
        себестоимость, налог на прибыль, закрытие. Баланс сходится."""
        return [
            ("2026-01-05", "Уставный капитал (объявлен)", [("75", "80", "1000000")]),
            ("2026-01-05", "Взнос учредителя на р/с", [("51", "75", "1000000")]),
            ("2026-01-10", "Закупка товара у поставщика", [("41", "60", "600000"), ("19", "60", "120000")]),
            ("2026-01-12", "Оплата поставщику (с НДС)", [("60", "51", "720000")]),
            ("2026-01-15", "НДС принят к вычету", [("68", "19", "120000")]),
            ("2026-01-18", "Реализация покупателю (вкл. НДС 20%)", [("62", "90.1", "1200000"), ("90.3", "68", "200000")]),
            ("2026-01-20", "Поступление оплаты от покупателя", [("51", "62", "1200000")]),
            ("2026-01-25", "Начислена зарплата", [("20", "70", "150000")]),
            ("2026-01-26", "Начислены страховые взносы (30%)", [("20", "69", "45000")]),
            ("2026-01-28", "Себестоимость проданных товаров", [("90.2", "41", "500000")]),
            ("2026-01-28", "Себестоимость выполненных работ", [("90.2", "20", "195000")]),
            ("2026-01-30", "Начислен налог на прибыль (20%)", [("99", "68", "61000")]),
            ("2026-01-31", "Закрытие продаж: прибыль", [("90.9", "99", "305000")]),
        ]

    # ---------- случайные проводки ----------
    def random_flow(self, chart: Chart, n: int = 50,
                    d_from: date = None, d_to: date = None) -> List[dict]:
        d_from = d_from or date(2026, 2, 1)
        d_to = d_to or date(2026, 12, 31)
        pairs = [
            # покупатели (дебиторка 62)
            ("51", "62.01", "buyer", "ООО Ромашка"), ("51", "62.01", "buyer", "ЗАО Вектор"),
            ("62.01", "90.1", "buyer", "ООО Ромашка"), ("62.01", "90.1", "buyer", "ЗАО Вектор"),
            ("62.01", "90.1", "buyer", "ИП Иванов"), ("51", "62.01", "buyer", "ИП Иванов"),
            # поставщики (кредиторка 60)
            ("10", "60.01", "supplier", "ООО Снабжение"), ("41", "60.01", "supplier", "ТД Мегаполис"),
            ("60.01", "51", "supplier", "ООО Снабжение"), ("60.01", "51", "supplier", "ТД Мегаполис"),
            # затраты и персонал
            ("20", "70", "employee", "Сотрудники"), ("20", "69", "employee", "Сотрудники"),
            ("26", "10", "employee", "Офис"), ("44", "60.01", "supplier", "ООО Маркетинг"),
            # деньги
            ("50", "51", None, None), ("51", "50", None, None), ("51", "76", "partner", "Банк"),
            # прочие доходы/расходы
            ("76", "91.1", "partner", "Прочие контрагенты"), ("91.2", "51", "partner", "Прочие контрагенты"),
            # себестоимость и НДС
            ("90.2", "41", None, None), ("90.2", "20", None, None), ("90.3", "68", None, None),
        ]
        entries = []
        span = (d_to - d_from).days
        for i in range(n):
            d = d_from + timedelta(days=self.rng.randint(0, span))
            dr, cr, dim, val = self.rng.choice(pairs)
            if not chart.get(dr) or not chart.get(cr):
                continue
            amt = money(self.rng.randint(100, 90000))
            analytics = {}
            if dim:
                analytics[dim] = val
            entries.append((d.isoformat(), f"Случайная операция #{i+1}",
                            [(dr, cr, str(amt), analytics)]))
        return entries

    # ---------- внешние файлы для ETL ----------
    def bank_statement(self, path: str, rows: int = 8) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        headers = "Дата;Назначение платежа;Контрагент;№ док;Сумма"
        examples = [
            ("01.03.2026", "Оплата по счету №21", "ИП Иванов", "ПБ-201", "25000.00"),
            ("02.03.2026", "Выплата зарплаты", "ООО Ромашка", "ПБ-202", "-30000.00"),
            ("05.03.2026", "Покупка канцтоваров", "Магазин Офис", "ПБ-203", "-1500.00"),
            ("08.03.2026", "Оплата за услуги", "ООО Сервис", "ПБ-204", "12000.00"),
            ("10.03.2026", "Оплата по счету №22", "ИП Иванов", "ПБ-205", "18000.00"),
            ("12.03.2026", "Покупка канцтоваров", "Магазин Офис", "ПБ-206", "-2200.00"),
            ("15.03.2026", "Выплата зарплаты", "ООО Ромашка", "ПБ-207", "-30000.00"),
            ("18.03.2026", "Оплата за услуги", "ООО Сервис", "ПБ-208", "6000.00"),
        ]
        with open(p, "w", encoding="utf-8") as f:
            f.write(headers + "\n")
            for _ in range(rows):
                r = examples[self.rng.randrange(len(examples))]
                f.write(";".join(r) + "\n")
        return p

    def invoices_json(self, path: str, rows: int = 6) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        items = []
        for i in range(rows):
            items.append({
                "dt": f"2026-03-{self.rng.randint(1, 28):02d}",
                "note": "invoice payment",
                "sum": str(self.rng.randint(1000, 90000)),
                "id": f"INV-{i+1:03d}",
            })
        json.dump({"rows": items}, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return p


# ============================================================
# Проверки (оценка)
# ============================================================
class Checks:
    """Набор проверок данных. Каждая возвращает dict-результат."""

    def __init__(self, journal: Journal, chart: Chart, store: Store):
        self.journal = journal
        self.chart = chart
        self.store = store
        self.reports = Reports(journal, chart)

    def run_all(self) -> List[Dict]:
        results = []
        for name in ("double_entry", "accounts_exist", "positive_amounts",
                     "osv_totals", "balance", "dedup", "reports", "basel"):
            try:
                r = getattr(self, f"check_{name}")()
            except Exception as e:
                r = {"name": name, "ok": False, "error": str(e)}
            results.append(r)
        return results

    # 1. каждая проводка сбалансирована
    def check_double_entry(self) -> Dict:
        entries = self.journal.entries()
        bad = []
        for e in entries:
            if sum((l.amount for l in e.lines), money(0)) <= 0:
                bad.append(e.no)
        ok = len(bad) == 0 and bool(entries)
        return {"name": "double_entry", "ok": ok, "checked": len(entries),
                "bad": bad, "detail": "Дт/Кт строки сбалансированы" if ok else f"Некорректно: {bad[:5]}"}

    # 2. все счета существуют в системе счетов
    def check_accounts_exist(self) -> Dict:
        missing = set()
        for e in self.journal.entries():
            for l in e.lines:
                for c in (l.debit, l.credit):
                    if not self.chart.get(c):
                        missing.add(c)
        ok = not missing
        return {"name": "accounts_exist", "ok": ok, "checked": len(self.chart.all()),
                "bad": sorted(missing), "detail": "Все счета в плане" if ok else f"Нет в плане: {sorted(missing)[:10]}"}

    # 3. суммы строк положительные
    def check_positive_amounts(self) -> Dict:
        bad = []
        for e in self.journal.entries():
            for l in e.lines:
                if l.amount <= 0:
                    bad.append(e.no)
        ok = not bad
        return {"name": "positive_amounts", "ok": ok, "bad": bad,
                "detail": "Суммы положительные" if ok else f"Отрицательные в: {bad[:5]}"}

    # 4. итоговые обороты ОСВ Дт = Кт
    def check_osv_totals(self) -> Dict:
        from datetime import date
        d_min = min((e.date for e in self.journal.entries()), default=date.today())
        d_max = max((e.date for e in self.journal.entries()), default=date.today())
        rows = self.reports.osv(d_min, d_max)
        s_dr = sum(r["turn_dr"] for r in rows)
        s_cr = sum(r["turn_cr"] for r in rows)
        ok = s_dr == s_cr and bool(rows)
        return {"name": "osv_totals", "ok": ok, "checked": len(rows),
                "detail": f"Обороты Дт={s_dr} = Кт={s_cr}" if ok else f"Дт={s_dr} ≠ Кт={s_cr}"}

    # 5. баланс: актив = пассив
    def check_balance(self) -> Dict:
        entries = self.journal.entries()
        if not entries:
            return {"name": "balance", "ok": False, "detail": "Нет данных"}
        d_max = max(e.date for e in entries)
        b = self.reports.balance(d_max)
        ok = b["total_assets"] == b["total_liab"]
        return {"name": "balance", "ok": ok, "checked": 1,
                "detail": f"Актив={b['total_assets']} = Пассив={b['total_liab']}"
                          if ok else f"Актив={b['total_assets']} ≠ Пассив={b['total_liab']}"}

    # 6. дедупликация рефов (в аналитике ключа ref)
    def check_dedup(self) -> Dict:
        seen, dup = {}, []
        for e in self.journal.entries():
            for l in e.lines:
                ref = l.analytics.get("ref")
                if ref:
                    if ref in seen:
                        dup.append(ref)
                    seen[ref] = e.no
        ok = not dup
        return {"name": "dedup", "ok": ok, "checked": len(seen), "bad": dup[:10],
                "detail": "Дубликатов рефов нет" if ok else f"Дубликаты: {dup[:10]}"}

    # 7. отчеты рендерятся (PDF+PNG)
    def check_reports(self) -> Dict:
        from .documents import Renderer, render_report, fmt_amount
        from datetime import date
        entries = self.journal.entries()
        if not entries:
            return {"name": "reports", "ok": False, "detail": "Нет данных"}
        d_min = min(e.date for e in entries)
        d_max = max(e.date for e in entries)
        made = []
        try:
            rows = self.reports.osv(d_min, d_max)
            r = Renderer(title="ОСВ (QA)", subtitle=f"{d_min} — {d_max}",
                         cols=["Счет", "Об Дт", "Об Кт"],
                         rows=[[x["code"], fmt_amount(x["turn_dr"]), fmt_amount(x["turn_cr"])] for x in rows])
            render_report("reports", "qa_osv", r, self.store)
            made.append("osv")
            b = self.reports.balance(d_max)
            r = Renderer(title="Баланс (QA)", subtitle=str(d_max),
                         cols=["Код", "Сумма"],
                         rows=[["ИТОГО", fmt_amount(b["total_assets"])]])
            render_report("reports", "qa_balance", r, self.store)
            made.append("balance")
        except Exception as e:
            return {"name": "reports", "ok": False, "error": str(e)}
        return {"name": "reports", "ok": True, "checked": len(made),
                "detail": "Рендер OK: " + ", ".join(made)}

    # 8. Basel нормативы считаются
    def check_basel(self) -> Dict:
        entries = self.journal.entries()
        if not entries:
            return {"name": "basel", "ok": False, "detail": "Нет данных"}
        d_max = max(e.date for e in entries)
        b = Basel(self.journal, self.chart).report(d_max)
        ratios = b["ratios"]
        ok = all(isinstance(v, (int, float)) or str(v).replace(".", "").isdigit() for v in ratios.values())
        return {"name": "basel", "ok": ok, "checked": 3,
                "detail": f"Н1.0={ratios['n10']}% Н1.1={ratios['n11']}% Н1.2={ratios['n12']}%"}


# ============================================================
# Комплекс загрузки
# ============================================================
class LoadComplex:
    """Исполняет план загрузки: шаги chart/templates/scenario/etl/manual."""

    def __init__(self, store: Store, plan: Dict):
        self.store = store
        self.plan = plan
        self.log = []
        self.plan_dir = Path(plan.get("dir", ""))

    @staticmethod
    def load_plan(path: str) -> Dict:
        plan = json.loads(Path(path).read_text(encoding="utf-8"))
        plan["dir"] = str(Path(path).parent)
        return plan

    def _path(self, p: str) -> str:
        """Путь из плана разрешается относительно каталога плана."""
        if not p:
            return p
        pp = Path(p)
        if pp.is_absolute():
            return str(pp)
        return str(self.plan_dir / pp)

    def run(self) -> Dict:
        store = self.store
        chart = None
        for step in self.plan.get("steps", []):
            kind = step.get("type")
            if kind == "chart":
                chart = builtin(step["system"]) if step.get("system") in ("ru", "us", "ifrs", "gaap") \
                    else load_file(step["system"])
                store.write_json("chart.json", chart.to_dict())
                self.log.append(f"chart: {chart.system} ({len(chart.all())} счетов)")
            elif kind == "templates":
                seed_templates(store)
                self.log.append("templates: базовый набор")
            elif kind == "scenario":
                chart = chart or Chart.from_dict(store.read_json("chart.json"))
                td = TestData(seed=int(step.get("seed", 42)))
                if step.get("scenario") == "closed_year":
                    items = td.closed_year()
                elif step.get("scenario") == "random":
                    items = td.random_flow(chart, n=int(step.get("n", 50)),
                                           d_from=date.fromisoformat(step["from"]),
                                           d_to=date.fromisoformat(step["to"]))
                else:
                    items = td.closed_year()
                self._post_all(chart, items)
                self.log.append(f"scenario: {len(items)} проводок")
            elif kind == "etl":
                from .etl import ETL
                chart = chart or Chart.from_dict(store.read_json("chart.json"))
                store.write_json("chart.json", chart.to_dict())
                etl = ETL(store, self._path(step["config"]))
                res = etl.run(self._path(step.get("file")))
                self.log.append(f"etl {step['config']}: {res['loaded']} загружено, {res['skipped']} пропущено")
            elif kind == "manual":
                chart = chart or Chart.from_dict(store.read_json("chart.json"))
                for item in step.get("entries", []):
                    d = date.fromisoformat(item["date"])
                    lines = [Line(x[0], x[1], money(x[2])) for x in item["lines"]]
                    self._post_all(chart, [(item["date"], item.get("desc", ""), item["lines"])])
                self.log.append(f"manual: {len(step.get('entries', []))} проводок")
        return {"steps": len(self.plan.get("steps", [])), "log": self.log}

    def _post_all(self, chart: Chart, items: List[tuple]) -> None:
        journal = Journal(self.store, chart)
        numbering = Numbering(self.store)
        for d_str, desc, pairs in items:
            d = date.fromisoformat(d_str)
            lines = []
            for p in pairs:
                if len(p) >= 4:
                    lines.append(Line(p[0], p[1], money(p[2]), dict(p[3])))
                else:
                    lines.append(Line(p[0], p[1], money(p[2])))
            no = numbering.next("entry", d)
            journal.post(d, lines, desc=desc, no=no, source="qa")


# ============================================================
# Общая функция прогона QA
# ============================================================
def run_qa(store: Store, plan: Dict) -> Dict:
    load_res = LoadComplex(store, plan).run()
    chart = Chart.from_dict(store.read_json("chart.json"))
    journal = Journal(store, chart)
    checks = Checks(journal, chart, store).run_all()
    ok_checks = sum(1 for c in checks if c.get("ok"))
    total_checks = len(checks)
    return {
        "name": plan.get("name", "QA"),
        "at": date.today().isoformat(),
        "dir": str(store.base),
        "load": load_res,
        "checks": checks,
        "entries": len(journal.entries()),
        "score": f"{ok_checks}/{total_checks}",
        "verdict": "PASS" if ok_checks == total_checks and not load_res["log"] == [] else "FAIL",
    }