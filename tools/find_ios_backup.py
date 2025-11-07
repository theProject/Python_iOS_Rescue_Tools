#!/usr/bin/env python3
r"""
find_ios_backup.py — Locate iOS/iTunes backups - cheeky little fellas - with a snake

Pretty by default. Pretty by theProject. Also supports --plain and --json for scripts.

Usage:
  python tools/find_ios_backup.py
  python tools/find_ios_backup.py --first
  python tools/find_ios_backup.py --json
  python tools/find_ios_backup.py --plain
  python tools/find_ios_backup.py --all-drives
"""
import argparse
import ctypes
import glob
import json
import os
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Iterable

@dataclass
class BackupEntry:
    Name: str       # hash folder
    FullPath: str   # absolute path (contains Manifest.db)
    LastWrite: str  # ISO timestamp from Manifest.db mtime

def _iso(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).isoformat(sep=" ", timespec="seconds")
    except Exception:
        return ""

def _exists(p: str) -> bool:
    return p and os.path.exists(p)

def _add_candidates_from_root(results: List[BackupEntry], backup_root: str):
    r"""Enumerate hash directories under a root like ...\MobileSync\Backup"""
    if not _exists(backup_root):
        return
    try:
        for name in os.listdir(backup_root):
            full = os.path.join(backup_root, name)
            if not os.path.isdir(full):
                continue
            mf = os.path.join(full, "Manifest.db")
            if os.path.isfile(mf):
                mtime = os.path.getmtime(mf)
                results.append(BackupEntry(Name=name, FullPath=os.path.abspath(full), LastWrite=_iso(mtime)))
    except PermissionError:
        pass

def _get_fixed_drives() -> List[str]:
    """Return drive roots like ['C:\\', 'D:\\'] (Windows only)."""
    drives = []
    bitmask = ctypes.cdll.kernel32.GetLogicalDrives()
    for i in range(26):
        if bitmask & (1 << i):
            root = f"{chr(65+i)}:\\"
            if os.path.isdir(root):
                drives.append(root)
    return drives

def find_backups(all_drives: bool = False) -> List[BackupEntry]:
    results: List[BackupEntry] = []

    HOME = os.environ.get("USERPROFILE", "")
    APPDATA = os.environ.get("APPDATA", "")
    LOCALAPPDATA = os.environ.get("LOCALAPPDATA", "")

    roots = [
        os.path.join(HOME, "Apple", "MobileSync", "Backup"),
        os.path.join(APPDATA, "Apple Computer", "MobileSync", "Backup"),
        os.path.join(LOCALAPPDATA, "Apple Computer", "MobileSync", "Backup"),
        os.path.join(LOCALAPPDATA, "Apple", "MobileSync", "Backup"),
    ]

    # OneDrive variants under same profile
    for od_root in glob.glob(os.path.join(HOME, "OneDrive*")):
        for tail in (
            os.path.join("Apple", "MobileSync", "Backup"),
            os.path.join("Desktop", "Apple", "MobileSync", "Backup"),
            os.path.join("Documents", "Apple", "MobileSync", "Backup"),
        ):
            roots.append(os.path.join(od_root, tail))

    # Dedup + probe
    seen = set()
    for r in roots:
        r = os.path.normpath(r)
        if r in seen:
            continue
        seen.add(r)
        _add_candidates_from_root(results, r)

    if all_drives:
        for drv in _get_fixed_drives():
            users_root = os.path.join(drv, "Users")
            if not _exists(users_root):
                continue
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

    uniq = {e.FullPath: e for e in results}
    out = sorted(uniq.values(), key=lambda x: x.LastWrite, reverse=True)
    return out

# --------------------- pretty printing ---------------------
def _term_width(default: int = 120) -> int:
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return default

def _truncate(s: str, width: int) -> str:
    if len(s) <= width:
        return s
    if width <= 1:
        return s[:width]
    return s[: max(0, width - 1)] + "…"

def _render_pretty(backups: List[BackupEntry]):
    if not backups:
        print("No backups found.\n› Make a local iPhone backup, then re-run this command.")
        return

    cols_total = _term_width()
    # Layout: Name | LastWrite | FullPath (FullPath expands)
    min_name, min_time, min_path = 22, 19, 20
    # allocate widths
    name_w = max(min_name, min((len(b.Name) for b in backups), default=min_name))
    time_w = max(min_time, 19)
    # leave padding & borders: 4 pipes + 6 spaces + 2 borders (~12 chars)
    overhead = 12 + name_w + time_w
    path_w = max(min_path, cols_total - overhead)

    top    = f"┌{'─'* (name_w+2)}┬{'─'* (time_w+2)}┬{'─'* (path_w+2)}┐"
    header = f"│ {'Name'.ljust(name_w)} │ {'LastWrite'.ljust(time_w)} │ {'FullPath'.ljust(path_w)} │"
    sep    = f"├{'─'* (name_w+2)}┼{'─'* (time_w+2)}┼{'─'* (path_w+2)}┤"
    rows: Iterable[str] = (
        f"│ {_truncate(b.Name, name_w).ljust(name_w)} │ "
        f"{_truncate(b.LastWrite, time_w).ljust(time_w)} │ "
        f"{_truncate(b.FullPath, path_w).ljust(path_w)} │"
        for b in backups
    )
    bottom = f"└{'─'* (name_w+2)}┴{'─'* (time_w+2)}┴{'─'* (path_w+2)}┘"

    print(top)
    print(header)
    print(sep)
    for line in rows:
        print(line)
    print(bottom)
    print(f"Found {len(backups)} backup(s). Newest shown first.\n")
    print("Tip:")
    print("  $BACKUP = python .\\tools\\find_ios_backup.py --first")
    print("  py .\\Python_iOS\\extract_ios_contacts.py --backup-dir \"$BACKUP\" --csv \"$env:USERPROFILE\\Desktop\\contacts.csv\" --vcf \"$env:USERPROFILE\\Desktop\\contacts.vcf\"")

def _render_plain(backups: List[BackupEntry]):
    if not backups:
        print("No backups found.")
        return
    col1, col2, col3 = "Name", "LastWrite", "FullPath"
    w1 = max(len(col1), max((len(b.Name) for b in backups), default=0))
    w2 = max(len(col2), max((len(b.LastWrite) for b in backups), default=0))
    print(f"{col1:<{w1}}  {col2:<{w2}}  {col3}")
    print(f"{'-'*w1}  {'-'*w2}  {'-'*40}")
    for b in backups:
        print(f"{b.Name:<{w1}}  {b.LastWrite:<{w2}}  {b.FullPath}")

# --------------------- cli ---------------------
def main():
    ap = argparse.ArgumentParser(description="Find iOS backup folders (hash dirs containing Manifest.db) on Windows.")
    ap.add_argument("--json", action="store_true", help="Output JSON")
    ap.add_argument("--first", action="store_true", help="Print only the newest FullPath (for scripting)")
    ap.add_argument("--all-drives", action="store_true", help="Scan all fixed drives (broader, slower)")
    ap.add_argument("--plain", action="store_true", help="Plain text table instead of pretty box drawing")
    args = ap.parse_args()

    backups = find_backups(all_drives=args.all_drives)

    if args.first:
        print(backups[0].FullPath if backups else "")
        return

    if args.json:
        print(json.dumps([asdict(b) for b in backups], indent=2))
        return

    if args.plain:
        _render_plain(backups)
    else:
        _render_pretty(backups)

if __name__ == "__main__":
    main()
