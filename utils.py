# utils.py — helpers for IO, time, html, csv, sqlite, logging
import csv, json, os, sqlite3, sys, hashlib, shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Dict, Any, Optional, List
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

def log_info(msg): console.log(f"[bold cyan]INFO[/]: {msg}")
def log_warn(msg): console.log(f"[bold yellow]WARN[/]: {msg}")
def log_err(msg):  console.log(f"[bold red]ERR[/]: {msg}")
def log_ok(msg):   console.log(f"[bold green]OK[/]: {msg}")

def ensure_dir(path: str):
    Path(path).mkdir(parents=True, exist_ok=True)
    return str(Path(path).resolve())

def write_csv(path: str, rows: Iterable[Dict[str, Any]]):
    rows = list(rows)
    if not rows:
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write("")
        return 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return len(rows)

def write_json(path: str, obj: Any, indent=2):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent, default=str)

def write_html_table(path: str, title: str, rows: List[Dict[str, Any]], brand=("#0b0b0b","#f5f5f5","#e20074","#05f2af")):
    bg, fg, mag, teal = brand
    html = ["<!doctype html><meta charset='utf-8'>",
            f"<title>{title}</title>",
            f"<style>body{{background:{bg};color:{fg};font:14px/1.5 -apple-system,Segoe UI,Arial,sans-serif;padding:24px}}",
            "h1{font-size:20px;margin:0 0 12px}",
            f".pill{{display:inline-block;margin-right:8px;padding:2px 8px;border-radius:12px;background:{mag};color:white}}",
            "table{border-collapse:collapse;width:100%;margin-top:10px}",
            "th,td{border:1px solid #333;padding:8px;text-align:left}",
            f"a{{color:{teal}}}",
            "</style>"]
    html.append(f"<h1>{title}</h1>")
    if not rows:
        html.append("<p>No records.</p>")
    else:
        html.append("<table><thead><tr>")
        for k in rows[0].keys():
            html.append(f"<th>{k}</th>")
        html.append("</tr></thead><tbody>")
        for r in rows:
            html.append("<tr>")
            for v in r.values():
                html.append(f"<td>{str(v) if v is not None else ''}</td>")
            html.append("</tr>")
        html.append("</tbody></table>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(html))

def open_sqlite(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn

APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)

def apple_time_to_dt(ts: Optional[float]) -> Optional[datetime]:
    if ts is None: return None
    try:
        # Some DBs store as seconds since 2001-01-01, others as nanoseconds
        if ts > 10**12:  # ns
            return APPLE_EPOCH + timedelta(seconds=ts/1e9)
        if ts > 10**9:   # ms
            return APPLE_EPOCH + timedelta(seconds=ts/1e3)
        return APPLE_EPOCH + timedelta(seconds=ts)
    except Exception:
        return None

def dt_to_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.astimezone(timezone.utc).isoformat() if dt else None

def hash_file(path: str, algo="sha256") -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

def copy_file(src: str, dst: str) -> str:
    ensure_dir(os.path.dirname(dst))
    shutil.copy2(src, dst)
    return dst

def walk_find(root: str, names: Iterable[str]) -> list:
    names = set(n.lower() for n in names)
    hits = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower() in names:
                hits.append(os.path.join(dirpath, fn))
    return hits

def table_print(title: str, rows: List[dict], limit: int = 10):
    table = Table(title=title, box=box.MINIMAL_DOUBLE_HEAD)
    if not rows:
        console.print(f"[bold]{title}[/] (0 rows)")
        return
    for k in rows[0].keys():
        table.add_column(k)
    for r in rows[:limit]:
        table.add_row(*[str(r.get(k, "")) for k in rows[0].keys()])
    console.print(table)