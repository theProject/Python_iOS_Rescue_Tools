import os, sqlite3
from pathlib import Path
from typing import Dict, List
from utils import open_sqlite, write_csv, write_json, write_html_table, ensure_dir, log_info, log_ok, log_warn

def parse_manifest(source: str, outdir: str) -> Dict[str, dict]:
    # Find Manifest.db by walking (some backups have multiple; take the first)
    manifest = None
    for root, _, files in os.walk(source):
        if "Manifest.db" in files:
            manifest = os.path.join(root, "Manifest.db")
            break
    if not manifest:
        raise FileNotFoundError("Manifest.db not found — are you pointing at the <BackupUUID> folder?")

    conn = open_sqlite(manifest)
    cur = conn.cursor()
    # iOS Manifest schema can be Files or file, try both
    table_name = None
    for cand in ("Files", "file", "FILE"):
        try:
            cur.execute(f"SELECT count(*) FROM {cand}"); cur.fetchone()
            table_name = cand; break
        except sqlite3.Error:
            continue
    if not table_name:
        raise RuntimeError("Unrecognized Manifest.db schema (no Files/file table).")

    rows = []
    try:
        cur.execute(f"SELECT fileID, domain, relativePath FROM {table_name}")
        for r in cur.fetchall():
            rows.append({"fileID": r["fileID"], "domain": r["domain"], "relativePath": r["relativePath"]})
    except sqlite3.Error:
        # Some schema: file contains relativePath in 'relativePath' or 'path'
        try:
            cur.execute(f"SELECT fileID, domain, relativePath as relativePath FROM {table_name}")
            for r in cur.fetchall():
                rows.append({"fileID": r["fileID"], "domain": r["domain"], "relativePath": r["relativePath"]})
        except sqlite3.Error:
            pass

    ensure_dir(outdir)
    write_csv(os.path.join(outdir, "manifest.csv"), rows)
    write_json(os.path.join(outdir, "manifest.json"), rows)
    write_html_table(os.path.join(outdir, "manifest.html"), "Manifest Index", rows)
    log_ok(f"Manifest parsed: {len(rows)} items")
    # Build quick lookup dict
    index = {}
    for r in rows:
        index[r["relativePath"]] = {"fileID": r["fileID"], "domain": r["domain"]}
    return index