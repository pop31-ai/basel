"""Файловое хранилище. Все данные — только файлы (JSON/JSONL), без СУБД."""
from __future__ import annotations
import json, os, threading, shutil
from pathlib import Path
from typing import List, Dict, Any, Optional


class Store:
    """База в каталоге.

    Структура:
      <base>/
        chart.json          — система счетов
        journal.jsonl       — append-only журнал проводок
        numbering.json      — счетчики нумерации
        templates.json      — шаблонные операции
        docs/               — сгенерированные документы (pdf/png)
        reports/            — отчеты
        tax/                — налоговая отчетность
    """

    def __init__(self, base: str = "buhdata"):
        self.base = Path(base)
        self._lock = threading.Lock()
        for d in ("", "docs", "reports", "tax"):
            (self.base / d).mkdir(parents=True, exist_ok=True)

    # ---------- журнал (append-only JSONL) ----------
    def journal_path(self) -> Path:
        return self.base / "journal.jsonl"

    def append_entry(self, data: Dict[str, Any]) -> None:
        with self._lock:
            with open(self.journal_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")
                f.flush()
                os.fsync(f.fileno())

    def read_entries(self) -> List[Dict[str, Any]]:
        p = self.journal_path()
        if not p.exists():
            return []
        with self._lock, open(p, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def truncate_journal(self) -> None:
        with self._lock:
            self.journal_path().write_text("", encoding="utf-8")

    # ---------- JSON-файлы ----------
    def read_json(self, name: str, default: Any = None) -> Any:
        p = self.base / name
        if not p.exists():
            return default
        with self._lock, open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    def write_json(self, name: str, data: Any) -> Path:
        p = self.base / name
        tmp = p.with_suffix(p.suffix + ".tmp")
        with self._lock, open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        shutil.move(str(tmp), str(p))
        return p

    def save_doc(self, kind: str, filename: str, data: bytes) -> Path:
        p = self.base / kind / filename
        with open(p, "wb") as f:
            f.write(data)
        return p

    def list_files(self, kind: str) -> List[Path]:
        d = self.base / kind
        return sorted(d.glob("*")) if d.exists() else []