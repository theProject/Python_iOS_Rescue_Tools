import os, sqlite3
from pathlib import Path
from typing import Dict, List, Optional
from utils import open_sqlite, write_csv, write_json, write_html_table, ensure_dir, log_info, log_ok, log_warn, apple_time_to_dt, dt_to_iso
from settings import SMS_DB_CANDIDATES
from tools.attachment_manager import safe_copy_by_basename

def _find_sms_db(source: str) -> Optional[str]:
    for root, _, files in os.walk(source):
        for cand in SMS_DB_CANDIDATES:
            if cand in files:
                return os.path.join(root, cand)
    return None

def extract_messages(source: str, outdir: str, resolve_contacts_json: Optional[str] = None):
    db_path = _find_sms_db(source)
    if not db_path:
        raise FileNotFoundError("sms.db not found")
    conn = open_sqlite(db_path)
    c = conn.cursor()
    # Basic schema fields
    # Gather handles
    handles = {}
    try:
        for r in c.execute("SELECT ROWID as id, id as handle FROM handle"):
            handles[r["id"]] = r["handle"]
    except sqlite3.Error:
        pass

    # Messages with joins (schema varies by iOS)
    messages = []
    attach_rows = []
    try:
        q = """
        SELECT
            m.ROWID as msg_id,
            m.date as date_apple,
            m.is_from_me as is_from_me,
            m.text as text,
            h.id as handle,
            a.filename as attachment_filename,
            a.transfer_name as attachment_name
        FROM message m
        LEFT JOIN handle h ON m.handle_id = h.ROWID
        LEFT JOIN message_attachment_join maj ON maj.message_id = m.ROWID
        LEFT JOIN attachment a ON a.ROWID = maj.attachment_id
        ORDER BY m.date ASC
        """
        for r in c.execute(q):
            dt = apple_time_to_dt(r["date_apple"])
            messages.append({
                "id": r["msg_id"],
                "datetime": dt_to_iso(dt),
                "is_from_me": r["is_from_me"],
                "handle": r["handle"],
                "text": r["text"],
                "attachment": r["attachment_name"] or (os.path.basename(r["attachment_filename"]) if r["attachment_filename"] else None),
                "attachment_path": r["attachment_filename"],
            })
            if r["attachment_filename"]:
                attach_rows.append(r)
    except sqlite3.Error:
        log_warn("Schema variant not supported; exporting message bodies only.")
        for r in c.execute("SELECT ROWID as msg_id, date as date_apple, is_from_me, text FROM message ORDER BY date ASC"):
            dt = apple_time_to_dt(r["date_apple"])
            messages.append({
                "id": r["msg_id"],
                "datetime": dt_to_iso(dt),
                "is_from_me": r["is_from_me"],
                "handle": None,
                "text": r["text"],
                "attachment": None,
                "attachment_path": None,
            })

    # Attachment copy best-effort
    attach_dir = os.path.join(outdir, "attachments")
    ensure_dir(attach_dir)
    for a in attach_rows:
        fn = a["attachment_filename"]
        if not fn: 
            continue
        base = os.path.basename(fn)
        copied = safe_copy_by_basename(source, base, attach_dir)
        if not copied:
            log_warn(f"Attachment not found in backup for: {base}")

    # Write outputs
    ensure_dir(outdir)
    write_csv(os.path.join(outdir, "messages.csv"), messages)
    write_json(os.path.join(outdir, "messages.json"), messages)
    write_html_table(os.path.join(outdir, "messages.html"), "Messages", messages[:2000])  # avoid huge HTMLs

    log_ok(f"Messages exported: {len(messages)} (attachments: {len(attach_rows)})")
    return messages