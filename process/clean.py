"""
Limpia raw_jobs.json, deduplica e inserta en SQLite.
Genera jobs_latest.json (solo las filas recién insertadas).
"""
from __future__ import annotations
import json, pathlib, sqlite3, hashlib, datetime
from typing import List, Dict

DB_PATH   = pathlib.Path("jobs.db")
RAW_PATH  = pathlib.Path("raw_jobs.json")
LATEST    = pathlib.Path("jobs_latest.json")

MANDATORY = {
    "job_id", "title", "company", "city",
    "posted_date", "source", "url", "description"
}

def ensure_schema(cx: sqlite3.Connection) -> None:
    cx.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id       TEXT PRIMARY KEY,
            title        TEXT, company TEXT,
            country      TEXT, city TEXT,
            contract     TEXT, posted_date DATE,
            source       TEXT, url TEXT,
            description  TEXT,
            score        REAL DEFAULT 0,
            inserted_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cx.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts
        USING fts5(description, content='jobs', content_rowid='rowid')
    """)

def insert_many(cx: sqlite3.Connection, rows: List[Dict]) -> List[Dict]:
    new_rows = []
    for r in rows:
        if not MANDATORY.issubset(r):
            continue
        try:
            cx.execute("""
                INSERT INTO jobs
                  (job_id,title,company,country,city,contract,
                   posted_date,source,url,description,score)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                r["job_id"], r["title"], r["company"],
                r.get("country",""), r["city"],
                r.get("contract",""),
                r["posted_date"], r["source"],
                r["url"], r["description"],
                r.get("score",0)
            ))
            rowid = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
            cx.execute("INSERT INTO jobs_fts(rowid, description) VALUES (?,?)",
                       (rowid, r["description"]))
            new_rows.append(r)
        except sqlite3.IntegrityError:
            # job_id ya existe → duplicado
            pass
    return new_rows

def main() -> None:
    if not RAW_PATH.exists():
        print("❌ raw_jobs.json no encontrado")
        return

    raw = json.loads(RAW_PATH.read_text())
    cx  = sqlite3.connect(DB_PATH)
    ensure_schema(cx)

    new_rows = insert_many(cx, raw)
    cx.commit()
    cx.close()

    LATEST.write_text(json.dumps(new_rows, ensure_ascii=False, indent=2))
    print(f"🧹 Insertados {len(new_rows)} nuevos de {len(raw)} totales")

if __name__ == "__main__":
    main()
