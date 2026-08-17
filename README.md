# buh — бухгалтерское ядро на Python

Двойная запись (Дт/Кт), системы счетов, аналитика, отчеты, BI, налоги, печать
документов в PDF/изображения, схемы проводок BPMN и Basel III отчетность.
Все данные — только в файлах (JSON/JSONL), без СУБД.

## Установка

Python ≥ 3.10. Для печати в PDF/PNG нужен `reportlab` и `Pillow`:

```
pip install reportlab pillow
```

## Быстрый старт

```
python -m buh --dir buhdata init --chart ru     # создание базы с планом счетов РФ (94н)
python -m buh --dir buhdata demo                 # демо-проводки + шаблоны
python -m buh --dir buhdata osv                  # оборотно-сальдовая ведомость (PDF+PNG)
python -m buh --dir buhdata balance              # баланс
python -m buh --dir buhdata basel                # Basel III нормативы
```

## Команды

| Команда | Назначение |
|---|---|
| `init --chart ru|us|ifrs` | создать базу и систему счетов |
| `chart list / load / export` | показать / загрузить / выгрузить систему счетов (json/csv) |
| `post "Дт 51 Кт 62 1000\|buyer=X; ..."` | записать проводку (посекундный ts) |
| `tmpl list / add / del / apply` | шаблонные операции (добавление/удаление/применение) |
| `osv [--from] [--to]` | оборотно-сальдовая ведомость |
| `balance [--asof]` | бухгалтерский баланс |
| `ofr [--from] [--to]` | отчет о финансовых результатах |
| `bi pivot / monthly / top` | BI: разрез по аналитике, помесячно, топ-счета |
| `tax vat / profit` | налоговые декларации (НДС, прибыль) + сдача (отметка о приеме) |
| `basel [--asof]` | Basel III: нормативы Н1.0/Н1.1/Н1.2 (инструкция ЦБ 199-И, упрощенно) |
| `doc inv / act / pay` | печать счетов, актов, платежек (PDF + PNG) |
| `bpmn <шаблон>` | схема проводок в нотации BPMN (SVG) |

Каталог данных по умолчанию — `buhdata/` (задается `--dir`).

## Системы счетов

Встроены: **государственная** — План счетов РФ (Приказ Минфина № 94н),
а также упрощенные `us`, `ifrs` и свободная `gaap`. В GAAP фиксированного плана
счетов нет — счета создаются автоматически при первой проводке (тип
определяется по префиксу: 1xx активы, 2xx пассивы, 3xx капитал, 4xx доходы,
5xx-6xx расходы, 9xx забаланс). Любая другая система загружается из файла:

```
python -m buh chart load my_chart.json   # формат: {"system":..,"accounts":[{code,name,kind,group}]}
python -m buh chart load my_chart.csv    # колонки: code,name,kind,group
```

Типы счетов: `A` актив, `P` пассив, `K` капитал, `R` доходы, `E` расходы, `Z` забалансовый.

## Аналитика

На каждой строке проводки — произвольный набор измерений:

```
python -m buh post "Дт 51 Кт 62 25000|buyer=ООО Ромашка;contract=12-А;project=Стройка"
```

BI разрез: `python -m buh bi pivot --dimension buyer`.

## Шаблонные операции

```
python -m buh tmpl add buy --name "Закупка у поставщика" --lines "Дт 10 Кт 60 {sum}"
python -m buh tmpl apply buy --params "sum=120000,supplier=ООО Поставщик" --date 2026-04-01
python -m buh tmpl del buy
```

В суммах допустима арифметика: `{sum}*0.2`, `{sum}/{1+0.2}`.

## Нумерация

Сквозная нумерация с префиксами/постфиксами и привязкой к периоду
(через API: `Numbering.set_format`). Формат: `{prefix}{seq}{suffix}{/year}`.
Например: `ПБ-000123/2026`, `АКТ-2026-007`.

## Структура данных (файлы)

```
<dir>/
  chart.json       — система счетов
  journal.jsonl    — append-only журнал проводок (Дт/Кт, ts с точностью до секунды)
  numbering.json   — счетчики нумерации
  templates.json   — шаблоны операций
  docs/            — печатные документы (pdf/png)
  reports/         — отчеты (pdf/png)
  tax/             — налоговые декларации и квитанции о приеме
```

## API (коротко)

```python
from buh import Store, Chart, Journal, Templates, Reports, BI, Tax
from buh.core import Line, money
from datetime import date

s = Store("buhdata"); chart = Chart.from_dict(s.read_json("chart.json"))
j = Journal(s, chart)
j.post(date(2026, 4, 1), [Line("51", "62", money(50000))], desc="оплата")
print(Reports(j, chart).balance(date(2026, 4, 30)))
```

## Модули

`core` — типы · `storage` — файлы · `charts` — системы счетов · `numbering` —
нумерация · `journal` — журнал и остатки · `templates` — шаблоны · `reports` —
ОСВ/баланс/ОФР · `bi` — BI · `tax` — налоги · `basel` — Basel III · `documents` —
печать · `bpmn` — схемы BPMN · `cli` — командная строка.

## Basel III (коротко)

`buh basel --asof 2026-01-31` считает нормативы достаточности капитала
по данным журнала (упрощенная модель, инструкция ЦБ РФ 199-И):

- Н1.0 (≥ 8%) — собственные средства / RWA · Н1.1 (≥ 4.5%) — базовый капитал / RWA
- Н1.2 (≥ 6%) — основной капитал / RWA
- RWA: касса/ДС 0%, прочие активы 100%, забаланс — по балансовой стоимости.
Отчет сохраняется в `reports/` (PDF, PNG, JSON).
