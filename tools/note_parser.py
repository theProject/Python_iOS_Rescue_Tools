import os, sqlite3
from utils import open_sqlite, ensure_dir, write_csv, write_json, write_html_table, log_ok, log_warn
from typing import List, Dict

def _find_note_db(source: str):
    for root, _, files in os.walk(source):
        for cand in ("NoteStore.sqlite","notes.sqlite"):
            if cand in files:
                return os.path.join(root, cand)
    return None

def extract_notes(source: str, outdir: str):
    db = _find_note_db(source)
    if not db:
        raise FileNotFoundError("Notes DB not found (NoteStore.sqlite / notes.sqlite)")
    conn = open_sqlite(db)
    cur = conn.cursor()
    rows: List[Dict] = []
    # Try modern schema first
    try:
        q = """
            SELECT ZNOTE.Z_PK as id, ZNOTE.ZTITLE as title, ZNOTEBODY.ZCONTENT as content
            FROM ZNOTE
            LEFT JOIN ZNOTEBODY ON ZNOTE.Z_PK = ZNOTEBODY.ZOWNER
        """
        for r in cur.execute(q):
            rows.append({"id": r["id"], "title": r["title"], "content": r["content"]})
    except Exception:
        # Fallback simplistic dump
        for r in cur.execute("SELECT * FROM ZNOTE"):
            rows.append(dict(r))
    ensure_dir(outdir)
    write_csv(os.path.join(outdir, "notes.csv"), rows)
    write_json(os.path.join(outdir, "notes.json"), rows)
    write_html_table(os.path.join(outdir, "notes.html"), "Notes", rows[:2000])
    log_ok(f"Notes exported: {len(rows)}")
    return rows