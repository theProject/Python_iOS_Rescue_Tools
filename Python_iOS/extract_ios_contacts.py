#!/usr/bin/env python3
# extract_ios_contacts.py
# Extract contacts from an UNENCRYPTED iTunes/iOS backup directory (Windows/macOS).
# Outputs CSV and/or VCF. No external deps; uses sqlite3 only.

import argparse
import csv
import os
import sqlite3
import sys
from typing import Dict, List, Optional, Tuple

def error(msg: str):
    print(f"[!] {msg}", file=sys.stderr)

def info(msg: str):
    print(f"[*] {msg}")

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
    # We query Files table (domain, relativePath, fileID)
    like_patterns = [
        "%AddressBook.sqlitedb%",
        "%AddressBookImages.sqlitedb%",
        "%Application Support/AddressBook/%",  # newer layout
        "%Contacts%.sqlite%",                  # catch-all
    ]
    rows: List[sqlite3.Row] = []
    for pat in like_patterns:
        rows += manifest_conn.execute("""
            SELECT fileID, domain, relativePath
            FROM Files
            WHERE relativePath LIKE ?
        """, (pat,)).fetchall()
    # Deduplicate by fileID, keep unique list
    seen = set()
    unique = []
    for r in rows:
        if r["fileID"] not in seen:
            unique.append(r)
            seen.add(r["fileID"])
    return unique

def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone()
    return row is not None

def load_contacts_from_ab_schema(conn: sqlite3.Connection) -> List[Dict]:
    """
    Legacy AddressBook schema (ABPerson / ABMultiValue).
    """
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

    mv_rows = conn.execute("""
        SELECT record_id, property, value, label
        FROM ABMultiValue
    """).fetchall()

    from collections import defaultdict
    phones = defaultdict(list)
    emails = defaultdict(list)
    addresses = defaultdict(list)
    urls = defaultdict(list)

    def norm_label(lbl: Optional[str]) -> str:
        if not lbl:
            return ""
        return lbl.strip().lower()

    for r in mv_rows:
        rid = r["record_id"]
        val = r["value"]
        label = norm_label(r["label"])
        prop = r["property"]

        is_phone = ("phone" in label) or ("mobile" in label) or ("cell" in label) or prop == 3 or prop == 7
        is_email = ("email" in label) or ("e-mail" in label) or prop == 4 or prop == 1
        is_addr  = ("address" in label) or prop == 6
        is_url   = ("url" in label) or ("homepage" in label)

        if not (is_phone or is_email or is_addr or is_url):
            if isinstance(val, str):
                if "@" in val:
                    is_email = True
                elif any(ch.isdigit() for ch in val) and len(val) >= 7:
                    is_phone = True

        if is_phone:
            phones[rid].append(val)
        elif is_email:
            emails[rid].append(val)
        elif is_addr:
            addresses[rid].append(val)
        elif is_url:
            urls[rid].append(val)

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

def load_contacts_from_coredata_schema(conn: sqlite3.Connection) -> List[Dict]:
    """
    Newer Core Data-backed schema (tables like ZABCDRECORD, ZABCDPHONENUMBER, ZABCDEMAILADDRESS).
    """
    info("Detected Core Data Z* schema")

    candidate_person_tables = ["ZABCDRECORD", "ZCONTACT", "ZPERSON", "ZABPERSON"]
    person_table = None
    for t in candidate_person_tables:
        if table_exists(conn, t):
            person_table = t
            break
    if not person_table:
        raise RuntimeError("Could not find person table in Core Data schema")

    def pick_col(cands: List[str]) -> Optional[str]:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({person_table})")}
        for c in cands:
            if c in cols:
                return c
        return None

    col_first = pick_col(["ZFIRSTNAME", "ZFIRST", "ZFIRST_NAME"])
    col_last  = pick_col(["ZLASTNAME", "ZLAST", "ZLAST_NAME"])
    col_middle = pick_col(["ZMIDDLENAME", "ZMN", "ZMIDDLE"])
    col_org   = pick_col(["ZORGANIZATION", "ZORGANIZATIONNAME", "ZCOMPANY"])
    col_note  = pick_col(["ZNOTE"])

    col_deleted = pick_col(["ZISDELETED", "ZTRASHED", "ZMARKEDFORDELETE"])

    base_query = f"SELECT Z_PK as id"
    for (alias, col) in [("first", col_first), ("last", col_last), ("middle", col_middle), ("org", col_org), ("note", col_note)]:
        if col:
            base_query += f", {col} as {alias}"
        else:
            base_query += f", '' as {alias}"
    if col_deleted:
        base_query += f", {col_deleted} as is_deleted"
    else:
        base_query += ", 0 as is_deleted"
    base_query += f" FROM {person_table}"

    persons = conn.execute(base_query).fetchall()

    map_defs = [
        ("phones", ["ZABCDPHONENUMBER", "ZPHONE", "ZABPHONE"], ["ZOWNER", "ZCONTACT", "ZPERSON"], ["ZFULLNUMBER", "ZVALUE", "ZPHONENUMBER"]),
        ("emails", ["ZABCDEMAILADDRESS", "ZEMAIL", "ZABEMAIL"], ["ZOWNER", "ZCONTACT", "ZPERSON"], ["ZADDRESS", "ZVALUE", "ZEMAIL"]),
        ("addresses", ["ZABCDPOSTALADDRESS", "ZPOSTALADDRESS", "ZADDRESS"], ["ZOWNER", "ZCONTACT", "ZPERSON"], ["ZSTREET", "ZVALUE", "ZFULLADDRESS"]),
        ("urls", ["ZABCDURLADDRESS", "ZURLADDRESS", "ZURL"], ["ZOWNER", "ZCONTACT", "ZPERSON"], ["ZURL", "ZVALUE"]),
    ]

    from collections import defaultdict
    child_maps: Dict[str, Dict[int, List[str]]] = {k: defaultdict(list) for k, *_ in map_defs}

    def locate_child_table(tbl_candidates, owner_candidates, value_candidates):
        for t in tbl_candidates:
            if table_exists(conn, t):
                cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({t})")}
                owner_col = next((c for c in owner_candidates if c in cols), None)
                value_col = next((c for c in value_candidates if c in cols), None)
                return t, owner_col, value_col
        return None, None, None

    for key, tbls, owners, values in map_defs:
        t, o, v = locate_child_table(tbls, owners, values)
        if t and o and v:
            for r in conn.execute(f"SELECT {o} as owner, {v} as value FROM {t}"):
                val = r["value"]
                if val:
                    child_maps[key][r["owner"]].append(str(val))
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

def export_csv(contacts: List[Dict], path: str):
    info(f"Writing CSV: {path}")
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

def pick_best_contacts_db(backup_dir: str, manifest_conn: sqlite3.Connection) -> Optional[str]:
    candidates = find_contact_dbs(manifest_conn)
    if not candidates:
        return None

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
    ap = argparse.ArgumentParser(description="Extract iOS contacts from an UNENCRYPTED backup directory.")
    ap.add_argument("--backup-dir", required=True, help="Path to iTunes/iOS backup directory (contains Manifest.db)")
    ap.add_argument("--csv", help="Path to write CSV (e.g., contacts.csv)")
    ap.add_argument("--vcf", help="Path to write VCF (e.g., contacts.vcf)")
    args = ap.parse_args()

    if not args.csv and not args.vcf:
        error("Specify at least one of --csv or --vcf")
        sys.exit(2)

    backup_dir = os.path.abspath(args.backup_dir)
    try:
        manifest_path = find_manifest_db(backup_dir)
    except FileNotFoundError as e:
        error(str(e))
        sys.exit(1)

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

    if args.csv:
        export_csv(contacts, args.csv)
    if args.vcf:
        export_vcf(contacts, args.vcf)

    info("Done.")

if __name__ == "__main__":
    main()
