import os, sqlite3
from utils import open_sqlite, ensure_dir, write_csv, write_json, write_html_table, log_ok
from typing import List, Dict
from utils import apple_time_to_dt, dt_to_iso

def _find_calendar_db(source: str):
    for root, _, files in os.walk(source):
        if "Calendar.sqlite" in files:
            return os.path.join(root, "Calendar.sqlite")
    return None

def extract_calendar(source: str, outdir: str):
    db = _find_calendar_db(source)
    if not db:
        raise FileNotFoundError("Calendar.sqlite not found")
    conn = open_sqlite(db)
    cur = conn.cursor()
    rows: List[Dict] = []
    try:
        q = """
        SELECT
            e.ROWID as id,
            e.summary as title,
            e.description as description,
            e.start_date as start_apple,
            e.end_date as end_apple,
            c.title as calendar
        FROM Event e
        LEFT JOIN Calendar c ON e.calendar_id = c.ROWID
        """
        for r in cur.execute(q):
            rows.append({
                "id": r["id"],
                "title": r["title"],
                "description": r["description"],
                "start": dt_to_iso(apple_time_to_dt(r["start_apple"])),
                "end": dt_to_iso(apple_time_to_dt(r["end_apple"])),
                "calendar": r["calendar"],
            })
    except Exception:
        # Fallback: dump some columns
        for r in cur.execute("SELECT ROWID as id, summary as title, start_date, end_date FROM Event"):
            rows.append({
                "id": r["id"],
                "title": r["title"],
                "start": dt_to_iso(apple_time_to_dt(r["start_date"])),
                "end": dt_to_iso(apple_time_to_dt(r["end_date"])),
            })
    ensure_dir(outdir)
    write_csv(os.path.join(outdir, "calendar.csv"), rows)
    write_json(os.path.join(outdir, "calendar.json"), rows)
    write_html_table(os.path.join(outdir, "calendar.html"), "Calendar Events", rows[:2000])
    log_ok(f"Calendar exported: {len(rows)}")
    return rows