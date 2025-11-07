#!/usr/bin/env python3
"""
find_ios_backup.py — Locate iOS/iTunes/Apple Devices backup folders on Windows, cheeky little things

Outputs backup entries (hash folder name, full path, last modified from Manifest.db).
Works without extra dependencies. Helps set Python_Rescue_Tools up with valid path.

Usage:
  python tools/find_ios_backup.py
  python tools/find_ios_backup.py --json
  python tools/find_ios_backup.py --first         # print newest FullPath only
  python tools/find_ios_backup.py --all-drives    # broader search (slower)

Tip (PowerShell):
  $BACKUP = python .\tools\find_ios_backup.py --first
  py .\Python_iOS\extract_ios_contacts.py --backup-dir "$BACKUP" --csv "$env:USERPROFILE\Desktop\contacts.csv"
"""

import argparse
import ctypes
import glob
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List

@dataclass
class BackupEntry:
    Name: str       # long hash folder name
    FullPath: str   # full path to the hash folder (contains Manifest.db)
    LastWrite: str  # ISO timestamp based on Manifest.db mtime

def _iso(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).isoformat(sep=" ", timespec="seconds")
    except Exception:
        return ""

def _exists(p: str) -> bool:
    return p and os.path.exists(p)

def _add_candidates_from_root(results: List[BackupEntry], backup_root: str):
    """Enumerate hash directories under a root like ...\MobileSync\Backup"""
    if not _exists(backup_root):
        return
    try:
        for name in os.listdir(backup_root):
            full = os.path.join(backup_root, name)
            if not os.path.isdir(full):
                continue
            manifest = os.path.join(full, "Manifest.db")
            if os.path.isfile(manifest):
                mtime = os.path.getmtime(manifest)
                results.append(BackupEntry(Name=name, FullPath=os.path.abspath(full), LastWrite=_iso(mtime)))
    except PermissionError:
        pass

def _get_fixed_drives() -> List[str]:
    """Return available drive roots like ['C:\\', 'D:\\'] (Windows only)."""
    drives = []
    bitmask = ctypes.cdll.kernel32.GetLogicalDrives()
    for i in range(26):
        if bitmask & (1 << i):
            root = f"{chr(65+i)}:\\"
            # Existence check; not filtering by drive type to avoid extra deps.
            if os.path.isdir(root):
                drives.append(root)
    return drives

def find_backups(all_drives: bool = False) -> List[BackupEntry]:
    results: List[BackupEntry] = []

    HOME = os.environ.get("USERPROFILE", "")
    APPDATA = os.environ.get("APPDATA", "")
    LOCALAPPDATA = os.environ.get("LOCALAPPDATA", "")

    # Common per-user locations: Apple Devices & iTunes variants
    roots = [
        os.path.join(HOME, "Apple", "MobileSync", "Backup"),
        os.path.join(APPDATA, "Apple Computer", "MobileSync", "Backup"),
        os.path.join(LOCALAPPDATA, "Apple Computer", "MobileSync", "Backup"),
        os.path.join(LOCALAPPDATA, "Apple", "MobileSync", "Backup"),
    ]

    # OneDrive flavors under the same Windows profile
    onedrive_glob = os.path.join(HOME, "OneDrive*")
    for od_root in glob.glob(onedrive_glob):
        for tail in [
            os.path.join("Apple", "MobileSync", "Backup"),
            os.path.join("Desktop", "Apple", "MobileSync", "Backup"),
            os.path.join("Documents", "Apple", "MobileSync", "Backup"),
        ]:
            roots.append(os.path.join(od_root, tail))

    # Dedup and probe
    seen = set()
    for r in roots:
        r = os.path.normpath(r)
        if r in seen:
            continue
        seen.add(r)
        _add_candidates_from_root(results, r)

    # Optional broad scan across drives (targeted pattern to keep it reasonable)
    if all_drives:
        for drv in _get_fixed_drives():
            users_root = os.path.join(drv, "Users")
            if not _exists(users_root):
                continue
            # Search a few common depths for ...\MobileSync\Backup
            patterns = [
                os.path.join(users_root, "*", "Apple", "MobileSync", "Backup"),
                os.path.join(users_root, "*", "AppData", "Roaming", "Apple Computer", "MobileSync", "Backup"),
                os.path.join(users_root, "*", "AppData", "Local", "Apple Computer", "MobileSync", "Backup"),
                os.path.join(users_root, "*", "OneDrive*", "Apple", "MobileSync", "Backup"),
                os.path.join(users_root, "*", "OneDrive*", "Desktop", "Apple", "MobileSync", "Backup"),
                os.path.join(users_root, "*", "OneDrive*", "Documents", "Apple", "MobileSync", "Backup"),
            ]
            for pat in patterns:
                for root in glob.glob(pat):
                    _add_candidates_from_root(results, root)

    # Unique by FullPath
    uniq = {}
    for e in results:
        uniq[e.FullPath] = e
    # Sort newest first
    out = sorted(uniq.values(), key=lambda x: x.LastWrite, reverse=True)
    return out

def main():
    ap = argparse.ArgumentParser(description="Find iOS backup folders (hash dirs containing Manifest.db) on Windows.")
    ap.add_argument("--json", action="store_true", help="Output JSON")
    ap.add_argument("--first", action="store_true", help="Print only the newest FullPath (for scripting)")
    ap.add_argument("--all-drives", action="store_true", help="Scan all fixed drives (broader, slower)")
    args = ap.parse_args()

    backups = find_backups(all_drives=args.all_drives)

    if args.first:
        if backups:
            print(backups[0].FullPath)
        else:
            print("")  # empty so shell vars won't break
        return

    if args.json:
        print(json.dumps([asdict(b) for b in backups], indent=2))
        return

    if not backups:
        print("No backups found. Make sure you've run a local iPhone backup on this Windows user.")
        return

    # Nicely formatted text table (no external libs)
    col1, col2, col3 = "Name", "LastWrite", "FullPath"
    w1 = max(len(col1), max((len(b.Name) for b in backups), default=0))
    w2 = max(len(col2), max((len(b.LastWrite) for b in backups), default=0))
    print(f"{col1:<{w1}}  {col2:<{w2}}  {col3}")
    print(f"{'-'*w1}  {'-'*w2}  {'-'*40}")
    for b in backups:
        print(f"{b.Name:<{w1}}  {b.LastWrite:<{w2}}  {b.FullPath}")

if __name__ == "__main__":
    main()
