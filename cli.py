"""Командная строка: buh init | chart | tmpl | post | osv | balance | ofr | bi | tax | doc | bpmn | demo"""
from __future__ import annotations
import argparse, json, sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from .core import Line, money, TemplateOp
from .storage import Store
from .charts import Chart, builtin, load_file
from .numbering import Numbering
from .journal import Journal
from .templates import Templates, seed_templates
from .reports import Reports
from .bi import BI
from .tax import Tax
from .documents import Renderer, render_report, fmt_amount
from . import bpmn as bpmn_mod

sys.path.insert(0, str(Path(__file__).parent))


def _ctx(args):
    store = Store(args.dir)
    chart_data = store.read_json("chart.json")
    if chart_data is None:
        print("Система счетов не загружена. Выполните: buh chart load ru")
        sys.exit(1)
    chart = Chart.from_dict(chart_data)
    numbering = Numbering(store)
    journal = Journal(store, chart)
    templates = Templates(store)
    reports = Reports(journal, chart)
    bi = BI(journal, chart)
    tax = Tax(store, journal)
    return store, chart, numbering, journal, templates, reports, bi, tax


def cmd_init(args):
    store = Store(args.dir)
    chart = builtin(args.chart)
    store.write_json("chart.json", chart.to_dict())
    print(f"Инициализировано: {store.base} (система счетов: {args.chart})")


def cmd_chart(args):
    store, chart, *_ = _ctx(args)
    if args.action == "list":
        print(f"{'Код':<7} {'Тип':<3} {'Наименование'}")
        for a in chart.all():
            print(f"{a.code:<7} {a.kind:<3} {a.name}")
    elif args.action == "load":
        if args.source in ("ru", "us", "ifrs"):
            ch = builtin(args.source)
        else:
            ch = load_file(args.source)
        store.write_json("chart.json", ch.to_dict())
        print(f"Загружена система счетов {args.source}: {len(ch.all())} счетов")
    elif args.action == "export":
        path = args.out or f"chart_{chart.system}.json"
        chart.save(path)
        print(f"Экспортировано в {path}")


def _parse_lines(raw: str):
    """Строки вида 'Дт 51 Кт 62 1000|buyer=ООО Ромашка; ...'"""
    lines = []
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        if "|" in part:
            head, an = part.split("|", 1)
            analytics = dict(kv.split("=", 1) for kv in an.split(";") if "=" in kv)
        else:
            head, analytics = part, {}
        toks = head.replace(",", ".").split()
        nums = [t for t in toks if t not in ("Дт", "Кт", "дт", "кт")]
        if len(nums) < 3:
            raise ValueError(f"Строка проводки должна быть: Дт <счет> Кт <счет> <сумма>: {part}")
        debit, credit, amount = nums[0], nums[1], money(nums[2])
        lines.append(Line(debit, credit, amount, analytics))
    return lines


def cmd_post(args):
    store, chart, numbering, journal, templates, *_ = _ctx(args)
    d = date.fromisoformat(args.date) if args.date else date.today()
    lines = _parse_lines(args.lines)
    no = numbering.next("entry", d)
    e = journal.post(d, lines, desc=args.desc or "", no=no, source="manual")
    print(f"Проводка {no} от {e.ts} записана")


def cmd_tmpl(args):
    store, chart, numbering, journal, templates, *_ = _ctx(args)
    if args.action == "list":
        for t in templates.list():
            print(f"{t.code:<16} {t.name}")
            for ln in t.lines:
                print(f"    Дт {ln['debit']:<4} Кт {ln['credit']:<4} {ln['amount']}")
    elif args.action == "add":
        desc = args.desc or ""
        lines = []
        for spec in args.lines.split(";"):
            if not spec.strip():
                continue
            toks = spec.split()
            debit, credit, amount = toks[0], toks[1], toks[2]
            lines.append({"debit": debit, "credit": credit, "amount": amount,
                          "analytics": {}})
        t = templates.add(args.code, args.name, desc, lines)
        print(f"Шаблон {t.code} добавлен")
    elif args.action == "del":
        ok = templates.remove(args.code)
        print("Удалено" if ok else "Не найдено")
    elif args.action == "apply":
        d = date.fromisoformat(args.date) if args.date else date.today()
        params = dict(kv.split("=", 1) for kv in (args.params or "").split(",") if "=" in kv)
        lines = templates.apply(args.code, params)
        no = numbering.next("entry", d)
        journal.post(d, lines, desc=f"шаблон {args.code}", no=no, source=f"template:{args.code}")
        print(f"Проводка {no} по шаблону {args.code}")


def cmd_osv(args):
    store, chart, numbering, journal, templates, reports, *_ = _ctx(args)
    d_from = date.fromisoformat(args.from_) if args.from_ else date(date.today().year, 1, 1)
    d_to = date.fromisoformat(args.to) if args.to else date.today()
    rows = reports.osv(d_from, d_to)
    cols = ["Счет", "Наим.", "Сн Дт", "Сн Кт", "Об Дт", "Об Кт", "Ск Дт", "Ск Кт"]
    data = [[r["code"], r["name"][:24], fmt_amount(r["open_dr"]), fmt_amount(r["open_cr"]),
             fmt_amount(r["turn_dr"]), fmt_amount(r["turn_cr"]),
             fmt_amount(r["close_dr"]), fmt_amount(r["close_cr"])] for r in rows]
    r = Renderer(title="Оборотно-сальдовая ведомость",
                 subtitle=f"{d_from} — {d_to}", cols=cols, rows=data,
                 meta={"Система счетов": chart.system, "Проводок": len(journal.entries())})
    paths = render_report("reports", "osv", r, store)
    print(f"ОСВ: строк {len(rows)}")
    print(f"  PDF: {paths['pdf']}")
    print(f"  PNG: {paths['png']}")


def cmd_balance(args):
    store, chart, numbering, journal, templates, reports, *_ = _ctx(args)
    as_of = date.fromisoformat(args.asof) if args.asof else date.today()
    b = reports.balance(as_of)
    cols = ["Код", "Наименование", "Сумма"]
    assets = [[c, n[:24], fmt_amount(v)] for c, n, v in b["assets"]]
    liab = [[c, n[:24], fmt_amount(v)] for c, n, v in b["liabilities"]]
    eq = [[c, n[:24], fmt_amount(v)] for c, n, v in b["equity"]]
    r = Renderer(title="Бухгалтерский баланс", subtitle=f"на {as_of}",
                 cols=cols, rows=assets + [["", "ИТОГО АКТИВ", fmt_amount(b["total_assets"])]] + liab + eq,
                 meta={"Актив": fmt_amount(b["total_assets"]), "Пассив": fmt_amount(b["total_liab"]),
                       "Прибыль (99)": fmt_amount(b["profit"])},
                 foot=[f"Баланс: {fmt_amount(b['total_assets'])} = {fmt_amount(b['total_liab'])}"])
    paths = render_report("reports", "balance", r, store)
    print(f"Баланс на {as_of}: актив {fmt_amount(b['total_assets'])}, пассив {fmt_amount(b['total_liab'])}")
    print(f"  PDF: {paths['pdf']}\n  PNG: {paths['png']}")


def cmd_ofr(args):
    store, chart, numbering, journal, templates, reports, *_ = _ctx(args)
    d_from = date.fromisoformat(args.from_) if args.from_ else date(date.today().year, 1, 1)
    d_to = date.fromisoformat(args.to) if args.to else date.today()
    r_ = reports.income(d_from, d_to)
    rows = [[c, "доход", fmt_amount(v)] for c, v in r_["detail_rev"].items()]
    rows += [[c, "расход", fmt_amount(v)] for c, v in r_["detail_exp"].items()]
    r = Renderer(title="Отчет о финансовых результатах", subtitle=f"{d_from} — {d_to}",
                 cols=["Счет", "Тип", "Сумма"], rows=rows,
                 foot=[f"Выручка: {fmt_amount(r_['revenue'])}   Расходы: {fmt_amount(r_['expenses'])}   "
                       f"Прибыль: {fmt_amount(r_['profit'])}"])
    paths = render_report("reports", "ofr", r, store)
    print(f"ОФР: прибыль {fmt_amount(r_['profit'])}")
    print(f"  PDF: {paths['pdf']}\n  PNG: {paths['png']}")


def cmd_bi(args):
    store, chart, numbering, journal, templates, reports, bi, *_ = _ctx(args)
    d_from = date.fromisoformat(args.from_) if args.from_ else date(date.today().year, 1, 1)
    d_to = date.fromisoformat(args.to) if args.to else date.today()
    if args.kind == "pivot":
        rows = bi.pivot(args.dimension, d_from, d_to, args.account)
        cols = [args.dimension, "Дт", "Кт", "Нетто"]
        data = [[r["key"][:28], fmt_amount(r["debit"]), fmt_amount(r["credit"]), fmt_amount(r["net"])] for r in rows]
    elif args.kind == "monthly":
        rows = bi.monthly(d_from, d_to)
        cols = ["Месяц", "Дт", "Кт"]
        data = [[r["month"], fmt_amount(r["debit"]), fmt_amount(r["credit"])] for r in rows]
    else:  # top
        rows = bi.top_accounts(d_from, d_to)
        cols = ["Счет", "Наименование", "Оборот"]
        data = [[r["code"], r["name"][:24], fmt_amount(r["amount"])] for r in rows]
    r = Renderer(title=f"BI: {args.kind}", subtitle=f"{d_from} — {d_to}", cols=cols, rows=data)
    paths = render_report("reports", f"bi_{args.kind}", r, store)
    print(f"  PDF: {paths['pdf']}\n  PNG: {paths['png']}")


def cmd_tax(args):
    store, chart, numbering, journal, templates, reports, bi, tax = _ctx(args)
    d_from = date.fromisoformat(args.from_) if args.from_ else date(date.today().year, 1, 1)
    d_to = date.fromisoformat(args.to) if args.to else date.today()
    if args.kind == "vat":
        rep = tax.vat(d_from, d_to)
    else:
        rep = tax.profit(d_from, d_to)
    result = tax.submit(rep)
    rows = []
    for k, v in rep.items():
        if k in ("period", "date"):
            continue
        if isinstance(v, Decimal) or isinstance(v, (int, float)):
            rows.append([k.upper(), fmt_amount(v)])
        else:
            rows.append([k.upper(), str(v)])
    r = Renderer(title=f"Налоговая декларация: {rep['type']}",
                 subtitle=f"период {d_from} — {d_to}",
                 cols=["Показатель", "Значение"], rows=rows,
                 meta=result["acceptance"])
    paths = render_report("tax", f"decl_{rep['type'].lower()}", r, store)
    print(f"Налог: {rep['type']} к уплате {fmt_amount(rep.get('payable', rep.get('tax', 0)))}")
    print(f"  файл: {result['file']}\n  статус: {result['acceptance']['status']}\n  PDF: {paths['pdf']}")


def cmd_doc(args):
    store, chart, numbering, journal, templates, *_ = _ctx(args)
    d = date.fromisoformat(args.date) if args.date else date.today()
    if args.kind == "inv":
        no = numbering.next("inv", d)
        cols = ["№", "Товар", "Ед.", "Цена", "Кол-во", "Сумма"]
        rows = []
        for item in (args.items or "").split(";"):
            if not item.strip():
                continue
            t = item.split()
            rows.append([len(rows) + 1, t[0][:20], t[1], t[2], t[3], fmt_amount(money(t[2]) * money(t[3]))])
        total = money(sum(r[5].replace(" ", "").replace(",", ".") if False else float(r[5].replace("−", "-").replace(" ", "")) for r in rows))
        r = Renderer(title="СЧЕТ на оплату", subtitle=f"№ {no} от {d}", cols=cols, rows=rows,
                     meta={"Поставщик": args.supplier or "ООО Поставщик", "Покупатель": args.buyer or "ООО Покупатель"},
                     foot=[f"ИТОГО: {fmt_amount(total)}"])
    elif args.kind == "act":
        no = numbering.next("act", d)
        r = Renderer(title="АКТ выполненных работ", subtitle=f"№ {no} от {d}",
                     meta={"Исполнитель": args.supplier or "ООО Исполнитель",
                           "Заказчик": args.buyer or "ООО Заказчик",
                           "Сумма": args.sum and fmt_amount(money(args.sum)) or "—"},
                     cols=["№", "Работа", "Сумма"],
                     rows=[[1, (args.items or "Выполненные работы")[:40],
                            fmt_amount(money(args.sum or 0))]],
                     foot=["Подпись Исполнителя ______   Подпись Заказчика ______"])
    else:
        no = numbering.next("pay", d)
        r = Renderer(title="ПЛАТЕЖНОЕ ПОРУЧЕНИЕ", subtitle=f"№ {no} от {d}",
                     meta={"Плательщик": args.supplier or "ООО Плательщик",
                           "Получатель": args.buyer or "ООО Получатель",
                           "Сумма": fmt_amount(money(args.sum or 0))})
    paths = render_report("docs", args.kind + "_" + no.replace("/", "-"), r, store)
    print(f"Документ: PDF {paths['pdf']}\n          PNG {paths['png']}")


def cmd_bpmn(args):
    store, chart, numbering, journal, templates, *_ = _ctx(args)
    tp = templates.get(args.template)
    params = dict(kv.split("=", 1) for kv in (args.params or "").split(",") if "=" in kv)
    svg = bpmn_mod.scheme_from_template(tp, params)
    out = args.out or f"{store.base}/docs/scheme_{tp.code}.svg"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(svg, encoding="utf-8")
    print(f"BPMN-схема сохранена: {out}")


def cmd_demo(args):
    """Наполняет демо-данными: проводки, шаблоны, отчеты."""
    store, chart, numbering, journal, templates, reports, bi, tax = _ctx(args)
    seed_templates(store)
    templates.reload()
    demo_entries = [
        ("2026-01-05", "Уставный капитал (взнос учредителя)", [("75", "80", "1000000")]),
        ("2026-01-05", "Поступление взноса на расчетный счет", [("51", "75", "1000000")]),
        ("2026-01-10", "Закупка материалов", [("10", "60", "300000")]),
        ("2026-01-12", "Оплата поставщику", [("60", "51", "300000")]),
        ("2026-01-15", "Реализация товара покупателю (выручка)", [("62", "90", "600000")]),
        ("2026-01-15", "НДС с реализации", [("90", "68", "100000")]),
        ("2026-01-16", "Поступление оплаты от покупателя", [("51", "62", "600000")]),
        ("2026-01-20", "Начислена зарплата", [("20", "70", "150000")]),
        ("2026-01-25", "Списаны материалы в производство", [("20", "10", "200000")]),
        ("2026-01-31", "Закрытие финансового результата (прибыль)", [("90", "99", "100000")]),
    ]
    for d, desc, pairs in demo_entries:
        dt = date.fromisoformat(d)
        no = numbering.next("entry", dt)
        lines = [Line(p[0], p[1], money(p[2])) for p in pairs]
        journal.post(dt, lines, desc=desc, no=no, source="demo")
    print(f"Демо-данные: {len(demo_entries)} проводок")


def cmd_basel(args):
    store, chart, numbering, journal, templates, reports, bi, tax = _ctx(args)
    from .basel import Basel
    as_of = date.fromisoformat(args.asof) if args.asof else date.today()
    b = Basel(journal, chart).report(as_of)
    rows_a = [[r["code"], r["name"][:22], fmt_amount(r["amount"]),
               f"{r['weight']*100:g}%", fmt_amount(r["rwa"])] for r in b["asset_detail"]]
    cols = ["Счет", "Наименование", "Актив", "Вес", "RWA"]
    rows_r = [["Н1.0 (собств. средства)", fmt_amount(b["own_funds"]), "≥ 8%", fmt_amount(b["ratios"]["n10"]) + "%"],
              ["Н1.1 (базовый капитал)", fmt_amount(b["capital"]["basic"]), "≥ 4.5%", fmt_amount(b["ratios"]["n11"]) + "%"],
              ["Н1.2 (основной капитал)", fmt_amount(b["capital"]["basic"] + b["capital"]["additional"]), "≥ 6%", fmt_amount(b["ratios"]["n12"]) + "%"],
              ["Прибыль", fmt_amount(b["capital"]["net_profit"]), "", ""]]
    r = Renderer(title="Basel III: нормативы достаточности капитала",
                 subtitle=f"на {as_of}  (инструкция ЦБ 199-И, упрощенно)",
                 cols=["Норматив", "Значение", "Порог", "Факт"],
                 rows=rows_r, meta={"RWA (взвешенные активы)": fmt_amount(b["rwa"]),
                                   "Нарушения": "; ".join(b["violations"]) or "нет"})
    paths = render_report("reports", "basel", r, store)
    store.write_json("reports/basel.json", b)
    print(f"Basel на {as_of}: Н1.0={fmt_amount(b['ratios']['n10'])}%, нарушений: "
          + ("; ".join(b["violations"]) or "нет"))
    print(f"  PDF: {paths['pdf']}\n  PNG: {paths['png']}\n  JSON: {store.base}/reports/basel.json")


def cmd_etl(args):
    from .etl import ETL
    etl = ETL(Store(args.dir), args.config)
    if args.action == "preview":
        for item in etl.preview(args.file, limit=args.limit):
            print(json.dumps(item, ensure_ascii=False, indent=2))
        return
    if args.action == "sample":
        _etl_sample(Store(args.dir), args.config)
        return
    res = etl.run(args.file, dry_run=args.dry)
    print(f"ETL '{etl.name}': источник {res['n_source']} записей, "
          f"загружено {res['loaded']}, пропущено {res['skipped']}, ошибок {len(res['errors'])}"
          + (" (сухой прогон)" if args.dry else ""))
    for err in res["errors"][:5]:
        print(f"  ошибка #{err['idx']}: {err['error']}")


def _etl_sample(store: Store, config: str) -> None:
    """Создает пример CSV-выписки по конфигу ETL."""
    import json as _json
    from pathlib import Path
    cfg = _json.loads(Path(config).read_text(encoding="utf-8"))
    src = cfg.get("source", {})
    path = Path(src.get("path", "etl_sample.csv"))
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = cfg.get("columns", {})
    rows = [
        ["01.04.2026", "Оплата по счету №12", "ИП Иванов", "ПБ-101", "50000.00"],
        ["02.04.2026", "Выплата зарплаты", "ООО Ромашка", "ПБ-102", "-30000.00"],
        ["03.04.2026", "Покупка канцтоваров", "Магазин Офис", "ПБ-103", "-2000.00"],
        ["04.04.2026", "Оплата за услуги", "ООО Сервис", "ПБ-104", "15000.00"],
    ]
    order = ["date", "desc", "counterparty", "ref", "amount"]
    header = ";".join(cols.get(k, k) for k in order)
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n")
        for r in rows:
            f.write(";".join(r) + "\n")
    print(f"Пример файла создан: {path}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="buh", description="Ядро бухгалтерского учета (файловая БД)")
    p.add_argument("--dir", default="buhdata", help="каталог данных")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("init", help="создать базу и загрузить систему счетов")
    sp.add_argument("--chart", default="ru")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("chart", help="система счетов")
    sp.add_argument("action", choices=["list", "load", "export"])
    sp.add_argument("source", nargs="?", default="ru")
    sp.add_argument("--out")
    sp.set_defaults(func=cmd_chart)

    sp = sub.add_parser("post", help="записать проводку: 'Дт 51 Кт 62 1000|buyer=X; ...'")
    sp.add_argument("lines")
    sp.add_argument("--date")
    sp.add_argument("--desc")
    sp.set_defaults(func=cmd_post)

    sp = sub.add_parser("tmpl", help="шаблонные операции")
    sp.add_argument("action", choices=["list", "add", "del", "apply"])
    sp.add_argument("code", nargs="?")
    sp.add_argument("--name")
    sp.add_argument("--desc")
    sp.add_argument("--lines", help="'Дт 62 Кт 90 {sum}; Дт 90 Кт 68 {sum}*0.2'")
    sp.add_argument("--params", help="'sum=120000,buyer=ООО Ромашка'")
    sp.add_argument("--date")
    sp.set_defaults(func=cmd_tmpl)

    sp = sub.add_parser("osv", help="оборотно-сальдовая ведомость")
    sp.add_argument("--from", dest="from_")
    sp.add_argument("--to")
    sp.set_defaults(func=cmd_osv)

    sp = sub.add_parser("balance", help="баланс")
    sp.add_argument("--asof")
    sp.set_defaults(func=cmd_balance)

    sp = sub.add_parser("ofr", help="отчет о финансовых результатах")
    sp.add_argument("--from", dest="from_")
    sp.add_argument("--to")
    sp.set_defaults(func=cmd_ofr)

    sp = sub.add_parser("bi", help="BI: pivot|monthly|top")
    sp.add_argument("kind", choices=["pivot", "monthly", "top"])
    sp.add_argument("--dimension", default="buyer")
    sp.add_argument("--account")
    sp.add_argument("--from", dest="from_")
    sp.add_argument("--to")
    sp.set_defaults(func=cmd_bi)

    sp = sub.add_parser("tax", help="налоги: vat|profit")
    sp.add_argument("kind", choices=["vat", "profit"])
    sp.add_argument("--from", dest="from_")
    sp.add_argument("--to")
    sp.set_defaults(func=cmd_tax)

    sp = sub.add_parser("doc", help="печать: inv|act|pay")
    sp.add_argument("kind", choices=["inv", "act", "pay"])
    sp.add_argument("--date")
    sp.add_argument("--supplier")
    sp.add_argument("--buyer")
    sp.add_argument("--items", help="inv: 'товар ед цена кол-во; ...' / act: описание")
    sp.add_argument("--sum")
    sp.set_defaults(func=cmd_doc)

    sp = sub.add_parser("bpmn", help="схема проводок BPMN (SVG)")
    sp.add_argument("template")
    sp.add_argument("--params")
    sp.add_argument("--out")
    sp.set_defaults(func=cmd_bpmn)

    sp = sub.add_parser("basel", help="Basel III: нормативы капитала")
    sp.add_argument("--asof")
    sp.set_defaults(func=cmd_basel)

    sp = sub.add_parser("etl", help="ETL: загрузка данных из внешних файлов")
    sp.add_argument("action", choices=["preview", "load", "sample"])
    sp.add_argument("config", help="путь к JSON-конфигу ETL")
    sp.add_argument("--file", help="исходный файл (переопределяет path в конфиге)")
    sp.add_argument("--dry", action="store_true", help="сухой прогон без записи")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_etl)

    sp = sub.add_parser("demo", help="демо-данные")
    sp.set_defaults(func=cmd_demo)

    args = p.parse_args(argv)
    if not getattr(args, "func", None):
        p.print_help()
        return 1
    try:
        args.func(args)
        return 0
    except Exception as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())