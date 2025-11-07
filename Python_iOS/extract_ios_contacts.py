#!/usr/bin/env python3
# extract_ios_contacts.py (PRT edition)
# Extract contacts from an UNENCRYPTED iTunes/iOS backup directory (Windows/macOS).
# Outputs CSV and/or VCF. No external deps; uses sqlite3 only.

import argparse
import csv
import os
import sqlite3
import sys
from typing import Dict, List, Optional

# -------------------- cute colors --------------------
RESET = "\x1b[0m"
MAGENTA = "\x1b[95m"   # bright magenta (closest to #e20074 in ANSI)
TEAL = "\x1b[96m"      # bright cyan ≈ teal
BOLD = "\x1b[1m"

def _enable_ansi_on_windows():
    # Try to enable ANSI on older Windows consoles; harmless elsewhere
    if os.name != "nt":
        return
    try:
        import msvcrt  # noqa: F401
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass

def _color(s, c):
    # Respect NO_COLOR or non-tty
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return s
    return f"{c}{s}{RESET}"

def error(msg: str):
    print(f"[!] {msg}", file=sys.stderr)

def info(msg: str):
    print(f"[*] {msg}")

# -------------------- core helpers --------------------
def find_manifest_db(backup_dir: str) -> str:
    candidate = os.path.join(backup_dir, "Manifest.db")
    if not os.path.isfile(candidate):
        raise FileNotFoundError("Manifest.db not found in backup directory")
    return candidate

def open_sqlite(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn

def backup_file_path(backup_dir: str, file_id: str) -> str:
    # Files are stored as <backup_dir>/<first 2 chars>/<fileID>
    subdir = file_id[:2]
    return os.path.join(backup_dir, subdir, file_id)

def find_contact_dbs(manifest_conn: sqlite3.Connection) -> List[sqlite3.Row]:
    # Look for likely Contacts DB paths across iOS versions
    like_patterns = [
        "%AddressBook.sqlitedb%",
        "%AddressBookImages.sqlitedb%",
        "%Application Support/AddressBook/%",
        "%Contacts%.sqlite%",
    ]
    rows: List[sqlite3.Row] = []
    for pat in like_patterns:
        rows += manifest_conn.execute("""
            SELECT fileID, domain, relativePath
            FROM Files
            WHERE relativePath LIKE ?
        """, (pat,)).fetchall()
    # Deduplicate by fileID
    seen = set(); unique = []
    for r in rows:
        if r["fileID"] not in seen:
            unique.append(r); seen.add(r["fileID"])
    return unique

def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone()
    return row is not None

# ---------- Legacy AddressBook schema ----------
def load_contacts_from_ab_schema(conn: sqlite3.Connection) -> List[Dict]:
    info("Detected legacy AB schema")
    contacts = []

    try:
        persons = conn.execute("""
            SELECT ROWID as id, First, Last, Middle, Organization, Note
            FROM ABPerson
        """).fetchall()
    except sqlite3.DatabaseError:
        persons = conn.execute("""
            SELECT ROWID as id, First, Last, Middle, Organization, Note
            FROM abperson
        """).fetchall()

    # ABMultiValueLabel: map numeric label ids -> text
    label_map: Dict[int, str] = {}
    if table_exists(conn, "ABMultiValueLabel"):
        try:
            cols = {r["name"].lower() for r in conn.execute("PRAGMA table_info(ABMultiValueLabel)")}
            label_col = "label" if "label" in cols else ("value" if "value" in cols else None)
            if label_col:
                for r in conn.execute(f"SELECT ROWID as id, {label_col} as txt FROM ABMultiValueLabel"):
                    if r["id"] is not None and r["txt"] is not None:
                        label_map[int(r["id"])] = str(r["txt"])
        except sqlite3.DatabaseError:
            pass

    mv_rows = conn.execute("""
        SELECT record_id, property, value, label
        FROM ABMultiValue
    """).fetchall()

    from collections import defaultdict
    phones = defaultdict(list)
    emails = defaultdict(list)
    addresses = defaultdict(list)
    urls = defaultdict(list)

    def norm_label(raw) -> str:
        if raw is None:
            return ""
        try:
            if isinstance(raw, int):
                return label_map.get(raw, str(raw)).strip().lower()
            s = str(raw)
            return s.strip().lower()
        except Exception:
            return ""

    for r in mv_rows:
        rid = r["record_id"]
        val = r["value"]
        if val is None:
            continue
        label = norm_label(r["label"])
        prop = r["property"]

        is_phone = ("phone" in label) or ("mobile" in label) or ("cell" in label) or prop in (3, 7)
        is_email = ("email" in label) or ("e-mail" in label) or prop in (1, 4)
        is_addr  = ("address" in label) or prop == 6
        is_url   = ("url" in label) or ("homepage" in label)

        if not (is_phone or is_email or is_addr or is_url):
            if isinstance(val, str):
                if "@" in val:
                    is_email = True
                elif sum(ch.isdigit() for ch in val) >= 7:
                    is_phone = True

        sval = str(val).strip()
        if not sval:
            continue

        if is_phone:
            phones[rid].append(sval)
        elif is_email:
            emails[rid].append(sval)
        elif is_addr:
            addresses[rid].append(sval)
        elif is_url:
            urls[rid].append(sval)

    for p in persons:
        contacts.append({
            "id": p["id"],
            "first": p["First"] or "",
            "middle": p["Middle"] or "",
            "last": p["Last"] or "",
            "org": p["Organization"] or "",
            "note": p["Note"] or "",
            "phones": phones.get(p["id"], []),
            "emails": emails.get(p["id"], []),
            "addresses": addresses.get(p["id"], []),
            "urls": urls.get(p["id"], []),
        })

    return contacts

# ---------- Newer Core Data Z* schema ----------
def load_contacts_from_coredata_schema(conn: sqlite3.Connection) -> List[Dict]:
    info("Detected Core Data Z* schema")

    candidate_person_tables = ["ZABCDRECORD", "ZCONTACT", "ZPERSON", "ZABPERSON"]
    person_table = next((t for t in candidate_person_tables if table_exists(conn, t)), None)
    if not person_table:
        raise RuntimeError("Could not find person table in Core Data schema")

    def pick_col(cands: List[str]) -> Optional[str]:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({person_table})")}
        for c in cands:
            if c in cols:
                return c
        return None

    col_first  = pick_col(["ZFIRSTNAME", "ZFIRST", "ZFIRST_NAME"])
    col_last   = pick_col(["ZLASTNAME", "ZLAST", "ZLAST_NAME"])
    col_mid    = pick_col(["ZMIDDLENAME", "ZMN", "ZMIDDLE"])
    col_org    = pick_col(["ZORGANIZATION", "ZORGANIZATIONNAME", "ZCOMPANY"])
    col_note   = pick_col(["ZNOTE"])
    col_del    = pick_col(["ZISDELETED", "ZTRASHED", "ZMARKEDFORDELETE"])

    base = f"SELECT Z_PK as id"
    base += f", {col_first} as first"  if col_first else ", '' as first"
    base += f", {col_last} as last"    if col_last  else ", '' as last"
    base += f", {col_mid} as middle"   if col_mid   else ", '' as middle"
    base += f", {col_org} as org"      if col_org   else ", '' as org"
    base += f", {col_note} as note"    if col_note  else ", '' as note"
    base += f", {col_del} as is_deleted" if col_del else ", 0 as is_deleted"
    base += f" FROM {person_table}"

    persons = conn.execute(base).fetchall()

    map_defs = [
        ("phones",   ["ZABCDPHONENUMBER", "ZPHONE", "ZABPHONE"], ["ZOWNER", "ZCONTACT", "ZPERSON"], ["ZFULLNUMBER", "ZVALUE", "ZPHONENUMBER"]),
        ("emails",   ["ZABCDEMAILADDRESS", "ZEMAIL", "ZABEMAIL"], ["ZOWNER", "ZCONTACT", "ZPERSON"], ["ZADDRESS", "ZVALUE", "ZEMAIL"]),
        ("addresses",["ZABCDPOSTALADDRESS","ZPOSTALADDRESS","ZADDRESS"], ["ZOWNER", "ZCONTACT", "ZPERSON"], ["ZSTREET", "ZVALUE", "ZFULLADDRESS"]),
        ("urls",     ["ZABCDURLADDRESS","ZURLADDRESS","ZURL"], ["ZOWNER", "ZCONTACT", "ZPERSON"], ["ZURL", "ZVALUE"]),
    ]

    from collections import defaultdict
    child_maps: Dict[str, Dict[int, List[str]]] = {k: defaultdict(list) for k, *_ in map_defs}

    def locate_child(tbls, owners, values):
        for t in tbls:
            if table_exists(conn, t):
                cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({t})")}
                o = next((c for c in owners if c in cols), None)
                v = next((c for c in values if c in cols), None)
                if o and v:
                    return t, o, v
        return None, None, None

    for key, tbls, owners, values in map_defs:
        t, o, v = locate_child(tbls, owners, values)
        if t and o and v:
            for r in conn.execute(f"SELECT {o} as owner, {v} as value FROM {t}"):
                if r["value"] is not None:
                    child_maps[key][r["owner"]].append(str(r["value"]))
        else:
            info(f"[warn] Could not find child table for {key}; skipping")

    contacts = []
    for p in persons:
        if p["is_deleted"]:
            continue
        pid = p["id"]
        contacts.append({
            "id": pid,
            "first": p["first"] or "",
            "middle": p["middle"] or "",
            "last": p["last"] or "",
            "org": p["org"] or "",
            "note": p["note"] or "",
            "phones": child_maps["phones"].get(pid, []),
            "emails": child_maps["emails"].get(pid, []),
            "addresses": child_maps["addresses"].get(pid, []),
            "urls": child_maps["urls"].get(pid, []),
        })
    return contacts

def read_contacts_from_db(db_path: str) -> List[Dict]:
    info(f"Reading contacts DB: {db_path}")
    conn = open_sqlite(db_path)
    try:
        if table_exists(conn, "ABPerson") or table_exists(conn, "abperson"):
            return load_contacts_from_ab_schema(conn)
        return load_contacts_from_coredata_schema(conn)
    finally:
        conn.close()

# -------------------- outputs --------------------
def export_csv(contacts: List[Dict], path: str):
    info(f"Writing CSV: {path}")
    folder = os.path.dirname(os.path.abspath(path))
    if folder and not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)
    cols = ["first", "middle", "last", "org", "phones", "emails", "addresses", "urls", "note"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for c in contacts:
            row = {k: c.get(k, "") for k in cols}
            for k in ["phones", "emails", "addresses", "urls"]:
                row[k] = " | ".join(c.get(k, []))
            w.writerow(row)

def vcard_escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace("\n", r"\n")

def export_vcf(contacts: List[Dict], path: str):
    info(f"Writing VCF: {path}")
    folder = os.path.dirname(os.path.abspath(path))
    if folder and not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for c in contacts:
            first = vcard_escape(c.get("first",""))
            last  = vcard_escape(c.get("last",""))
            middle = vcard_escape(c.get("middle",""))
            org   = vcard_escape(c.get("org",""))
            note  = vcard_escape(c.get("note",""))
            fn = " ".join([x for x in [first, middle, last] if x]).strip()
            f.write("BEGIN:VCARD\n")
            f.write("VERSION:3.0\n")
            f.write(f"N:{last};{first};{middle};;\n")
            f.write(f"FN:{fn}\n")
            if org:
                f.write(f"ORG:{org}\n")
            for p in c.get("phones", []):
                f.write(f"TEL;TYPE=CELL:{p}\n")
            for e in c.get("emails", []):
                f.write(f"EMAIL;TYPE=INTERNET:{e}\n")
            for u in c.get("urls", []):
                f.write(f"URL:{u}\n")
            if note:
                f.write(f"NOTE:{note}\n")
            for a in c.get("addresses", []):
                f.write(f"ITEM1.ADR;TYPE=HOME:;;;;;;{vcard_escape(a)}\n")
            f.write("END:VCARD\n")

# -------------------- manifest pick & CLI --------------------
def pick_best_contacts_db(backup_dir: str, manifest_conn: sqlite3.Connection) -> Optional[str]:
    candidates = find_contact_dbs(manifest_conn)
    if not candidates:
        return None

    # Prefer AddressBook/Contacts DB over images or auxiliary files
    priorities = []
    for r in candidates:
        rp = (r["relativePath"] or "").lower()
        score = 0
        if "addressbook.sqlitedb" in rp or "contacts" in rp:
            score += 10
        if "images" in rp:
            score -= 5
        if "application support/addressbook" in rp:
            score += 5
        score += rp.count("/")
        priorities.append((score, r))

    priorities.sort(key=lambda x: x[0], reverse=True)
    best = priorities[0][1]
    db_path = backup_file_path(backup_dir, best["fileID"])
    if not os.path.isfile(db_path):
        error(f"Expected DB file missing: {db_path}")
        return None
    info(f"Chosen DB from backup: domain={best['domain']} path={best['relativePath']}")
    return db_path

def main():
    _enable_ansi_on_windows()

    ap = argparse.ArgumentParser(description="Extract iOS contacts from an UNENCRYPTED backup directory.")
    ap.add_argument("--backup-dir", required=True, help="Path to iTunes/iOS backup directory (contains Manifest.db)")
    ap.add_argument("--csv", help="Path to write CSV (e.g., contacts.csv)")
    ap.add_argument("--vcf", help="Path to write VCF (e.g., contacts.vcf)")
    args = ap.parse_args()

    # Default outputs: Documents\PRT-Contacts\contacts.csv/.vcf
    user_docs = os.path.join(os.path.expanduser("~"), "Documents")
    outdir = os.path.join(user_docs, "PRT-Contacts")
    if not args.csv:
        args.csv = os.path.join(outdir, "contacts.csv")
    if not args.vcf:
        args.vcf = os.path.join(outdir, "contacts.vcf")

    backup_dir = os.path.abspath(args.backup_dir)
    try:
        manifest_path = find_manifest_db(backup_dir)
    except FileNotFoundError as e:
        error(str(e)); sys.exit(1)

    conn = open_sqlite(manifest_path)
    try:
        db_path = pick_best_contacts_db(backup_dir, conn)
    finally:
        conn.close()

    if not db_path:
        error("Could not locate a contacts database in Manifest.db. Is this the correct backup (and unencrypted)?")
        sys.exit(1)

    contacts = read_contacts_from_db(db_path)
    info(f"Found {len(contacts)} contacts")

    # Ensure output directory exists and write files
    export_csv(contacts, args.csv)
    export_vcf(contacts, args.vcf)

    # Fun, colorful outro
    pet = _color("Python", TEAL)
    brand = _color("theProject.", MAGENTA + BOLD)
    count = _color(str(len(contacts)), TEAL + BOLD)
    path_colored = _color(outdir, MAGENTA)

    print()
    print(f"{brand} has a pet called {pet}, and it had its way with your backup…")
    print(f"…and recovered {count} of your long-lost contacts. Breathe easy. 🫶")
    print(f"Your files are waiting in: {path_colored}")
    print()

if __name__ == "__main__":
    main()
