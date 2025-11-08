# settings.py — central configuration
from pathlib import Path

VERSION = "0.2.0"

# Candidate database/dir names we scan for inside MobileSync backup trees
CONTACT_DB_CANDIDATES = [
    "AddressBook.sqlitedb",     # very old iOS
    "AddressBook.sqlitedb-wal",
    "Contacts2.sqlite",         # some mac backups
    "Contacts.sqlite",          # modern
]

SMS_DB_CANDIDATES = [
    "sms.db",
    "chat.db",                  # rare variant
]

NOTES_DB_CANDIDATES = [
    "notes.sqlite",
    "NoteStore.sqlite",
]

CAL_DB_CANDIDATES = [
    "Calendar.sqlite",
]

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".heic", ".heif", ".tif", ".tiff", ".mov", ".mp4"}

DEFAULT_OUTPUT_FORMATS = {"csv", "json", "html"}

# HTML theming (on brand)
BRAND_MAGENTA = "#e20074"
BRAND_TEAL = "#05f2af"
BRAND_BG = "#0b0b0b"
BRAND_FG = "#f5f5f5"

def normalize_path(p):
    return str(Path(p).expanduser().resolve())