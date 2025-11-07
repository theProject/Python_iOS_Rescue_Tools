import os, sqlite3
from typing import List, Dict
from utils import walk_find, open_sqlite, write_csv, write_json, write_html_table, ensure_dir, log_info, log_ok, log_warn
from settings import CONTACT_DB_CANDIDATES

def _table_exists(conn, name: str) -> bool:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None

def _extract_abperson(conn) -> List[Dict]:
    # Legacy AddressBook schema
    people = []
    try:
        cur = conn.execute("SELECT ROWID as id, First, Last, Organization FROM ABPerson")
        base = {r["id"]: {"id": r["id"], "first": r["First"], "last": r["Last"], "organization": r["Organization"], "phones": [], "emails": []} for r in cur.fetchall()}
        # ABMultiValue holds phones/emails…
        try:
            cur = conn.execute("SELECT record_id as id, value, label, property FROM ABMultiValue")
            for r in cur.fetchall():
                if r["id"] in base:
                    if r["property"] in (3,):   # phones
                        base[r["id"]]["phones"].append(r["value"])
                    elif r["property"] in (4,): # emails
                        base[r["id"]]["emails"].append(r["value"])
        except sqlite3.Error:
            pass
        people = list(base.values())
    except sqlite3.Error:
        pass
    return people

def _extract_znames(conn) -> List[Dict]:
    # Modern Contacts.sqlite (AddressBook.framework CoreData)
    people = []
    try:
        cur = conn.execute("SELECT Z_PK as id, ZFIRSTNAME as first, ZLASTNAME as last, ZORGANIZATION as organization FROM ZABCDRECORD")
        ids = [r["id"] for r in cur.fetchall()]
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT Z_PK as id, ZFIRSTNAME as first, ZLASTNAME as last, ZORGANIZATION as organization FROM ZABCDRECORD")
        records = {r["id"]: dict(r) | {"phones": [], "emails": []} for r in cur.fetchall()}
        # Phones
        try:
            cur = conn.execute("SELECT ZOWNER as owner, ZFULLNUMBER as number FROM ZABCDPHONENUMBER WHERE ZFULLNUMBER IS NOT NULL")
            for r in cur.fetchall():
                if r["owner"] in records:
                    records[r["owner"]]["phones"].append(r["number"])
        except sqlite3.Error:
            pass
        # Emails
        try:
            cur = conn.execute("SELECT ZOWNER as owner, ZADDRESS as email FROM ZABCDEMAILADDRESS WHERE ZADDRESS IS NOT NULL")
            for r in cur.fetchall():
                if r["owner"] in records:
                    records[r["owner"]]["emails"].append(r["email"])
        except sqlite3.Error:
            pass
        people = list(records.values())
    except sqlite3.Error:
        pass
    return people

def extract_contacts(source: str, outdir: str, fmt: str = "csv"):
    hits = walk_find(source, CONTACT_DB_CANDIDATES)
    if not hits:
        raise FileNotFoundError("No contacts DB found (looked for AddressBook/Contacts.sqlite variants).")
    db = hits[0]
    conn = open_sqlite(db)
    conn.row_factory = sqlite3.Row

    people = _extract_abperson(conn)
    if not people:
        people = _extract_znames(conn)

    ensure_dir(outdir)
    rows = []
    for p in people:
        rows.append({
            "id": p.get("id"),
            "first": p.get("first"),
            "last": p.get("last"),
            "organization": p.get("organization"),
            "phones": ", ".join(p.get("phones", [])),
            "emails": ", ".join(p.get("emails", [])),
        })
    write_csv(os.path.join(outdir, "contacts.csv"), rows)
    write_json(os.path.join(outdir, "contacts.json"), people)
    write_html_table(os.path.join(outdir, "contacts.html"), "Contacts", rows)
    log_ok(f"Contacts exported: {len(rows)}")
    return rows