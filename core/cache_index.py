from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS pdf_cache (
    ruta_relativa TEXT PRIMARY KEY,
    filename TEXT,
    carpeta_origen TEXT,
    size_bytes INTEGER,
    mtime_ns INTEGER,
    cache_stem TEXT,
    raw_json TEXT,
    norm_json TEXT,
    meta_json TEXT,
    status TEXT,
    provider TEXT,
    model TEXT,
    updated_at TEXT,
    error_type TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_pdf_cache_status ON pdf_cache(status);
CREATE INDEX IF NOT EXISTS idx_pdf_cache_provider_model ON pdf_cache(provider, model);
"""


def init_index(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        con.executescript(SCHEMA)
        con.commit()


def upsert_entry(db_path: Path, entry: dict[str, Any]) -> None:
    init_index(db_path)
    cols = [
        "ruta_relativa", "filename", "carpeta_origen", "size_bytes", "mtime_ns", "cache_stem",
        "raw_json", "norm_json", "meta_json", "status", "provider", "model", "updated_at", "error_type", "error"
    ]
    payload = {c: entry.get(c) for c in cols}
    placeholders = ",".join([":" + c for c in cols])
    updates = ",".join([f"{c}=excluded.{c}" for c in cols if c != "ruta_relativa"])
    sql = f"INSERT INTO pdf_cache ({','.join(cols)}) VALUES ({placeholders}) ON CONFLICT(ruta_relativa) DO UPDATE SET {updates}"
    with sqlite3.connect(db_path) as con:
        con.execute(sql, payload)
        con.commit()


def get_entry(db_path: Path, ruta_relativa: str) -> dict[str, Any] | None:
    if not db_path.exists():
        return None
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM pdf_cache WHERE ruta_relativa=?", (ruta_relativa,)).fetchone()
    return dict(row) if row else None


def is_fast_reusable(db_path: Path, ruta_relativa: str, size_bytes: int, mtime_ns: int, provider: str, model: str, validate_files: bool = True) -> dict[str, Any] | None:
    row = get_entry(db_path, ruta_relativa)
    if not row:
        return None
    if row.get("status") != "success":
        return None
    if int(row.get("size_bytes") or -1) != int(size_bytes):
        return None
    if int(row.get("mtime_ns") or -1) != int(mtime_ns):
        return None
    if (row.get("provider") or "").lower() != (provider or "").lower():
        return None
    if (row.get("model") or "") != (model or ""):
        return None
    if validate_files:
        for k in ["raw_json", "norm_json", "meta_json"]:
            p = row.get(k)
            if not p or not Path(p).exists():
                return None
    return row


def iter_entries(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM pdf_cache ORDER BY ruta_relativa").fetchall()
    return [dict(r) for r in rows]
