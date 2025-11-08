#  Python iOS Rescue Tools — Contacts Ready
> **“Extract. Decode. Recover.”**  
> A modular Python toolkit for ethical iOS data recovery (opensource and clean - we get em all, no hidden $50 fees here) — built for investigators, technicians, and curious minds who don’t accept “unrecoverable.”
> Not built for those intending on breaking the law, invading privacy - or just general anti-social creep behavior. We check for that.

---

## 🚀 Overview

**Python iOS Rescue Tools** is as close to a forensic-grade recovery framework for iOS data, written in Python for justice against burnware out there that gives you 3 comtacts free, and ransoms the rest.  Inspired by a good friend who truly needed help, we solved a problem for him - and sharing for all.
It can analyze, decode, and export artifacts from iTunes/iOS backups or direct file extractions, producing clean, structured outputs for auditing, reporting, or digital-forensics workflows. 

Developed by **theProject.** — where **code meets craft.**

---

## 🧩 Core Features

- 🔍 **Automatic backup detection** (`Manifest.db`, `Info.plist`)
- 📂 **Extraction modules** for Contacts, Messages, Notes, and App Data
- 🧠 **Smart decoding** of Apple binary plists, SQLite, and message archives
- 💾 **Multiple export formats:** `VFC`, `CSV`, `JSON`, `HTML`
- 🛠 **Modular “Tools” system** for extending capabilities (scripts, parsers, or utilities)
- 🧪 Built for **forensic transparency** — nothing hidden, everything logged

---

## ⚙️ Installation

```bash
git clone https://github.com/theProject/python-ios-rescue-tools.git
cd python-ios-rescue-tools
pip install -r requirements.txt
```

##🧠 Command Reference

| Command                 | Purpose                                | Why It Matters                                                                    |
| ----------------------- | -------------------------------------- | --------------------------------------------------------------------------------- |
| `analyze`               | Indexes and fingerprints an iOS backup | Builds a map of file hashes, original paths, and structure for faster extraction. |
| `contacts`              | Extracts and normalizes contacts       | Recovers AddressBook entries with metadata and links for human-readable export.   |
| `messages`              | Recovers SMS / iMessage threads        | Parses `sms.db`, reconstructs chat logs, and associates handles + timestamps.     |
| `notes`                 | Extracts Notes database                | Parses Notes SQLite stores for quick recovery or forensic reconstruction.         |
| `report`                | Compiles summary of all exports        | Merges contacts, messages, and metadata into a readable HTML or JSON report.      |
| `--format`              | Sets export format                     | Supports `vfc`, `csv`, `json`, and `html` (see below).                            |
| `--output`              | Defines output path                    | Keeps your recovered data neatly organized.                                       |
| `--verbose` / `--quiet` | Toggle logging                         | Control how much detail you see in the console.                                   |

---

##💾 Output Formats

| Format   | Description                                                                            |
| -------- | -------------------------------------------------------------------------------------- |
| **VFC**  | *Virtual Forensic Container* — standardized for tools like Magnet AXIOM or Cellebrite. |
| **CSV**  | Plain text, spreadsheet-friendly — perfect for auditing or reports.                    |
| **JSON** | Structured output for pipelines, APIs, or dashboards.                                  |
| **HTML** | Human-readable web-style summary for visualization and sharing.                        |

---

```python
python rescue.py contacts --source /path/to/ios_backup --output results/ --format csv
```

## 🖥️ Platform Support

Python iOS Rescue Tools is **cross-platform** — it reads Apple backup artifacts directly, so it works on macOS (Finder), Windows (iTunes), and Linux (if you copy the backup folder over).  Yes a backup - not just a copy and paste of plugging yor phone in - as the treats it as a USB flash storage of photos.
### Default backup locations
- **macOS (Finder / iTunes on macOS):**  
  `~/Library/Application Support/MobileSync/Backup/<BackupUUID>/`
- **Windows (iTunes):**  
  `C:\Users\<you>\AppData\Roaming\Apple Computer\MobileSync\Backup\<BackupUUID>\`
- **Linux / External Drive:**  
  Any mounted path containing the `Backup/<BackupUUID>/` folder — point `--source` at it.

### Permissions & platform notes
- **Full Disk Access on macOS:** If you get `Permission denied`, add your terminal/IDE to System Settings → Privacy & Security → Full Disk Access.
- **Encrypted backups:** Supported *only if* you provide the backup password. Without the password Keychain and some DBs remain encrypted and unreadable.
- **Apple Silicon:** Works with Python 3.10+ (install system Python or brew python — no special build needed).
- **iCloud-only data:** Not present in local backups. Photos/messages backed up to iCloud but *not* in the local MobileSync folder will not be recoverable by this tool unless the user exports from iCloud first.

### Quick platform CLI examples

macOS (Finder backup)
```bash
python rescue.py analyze "~/Library/Application Support/MobileSync/Backup/<BackupUUID>/"
python rescue.py contacts --source "~/Library/Application Support/MobileSync/Backup/<BackupUUID>/" --output ~/Desktop/Rescue --format csv
```
Windows (iTunes Backup)
```python
python rescue.py analyze "C:\Users\<you>\AppData\Roaming\Apple Computer\MobileSync\Backup\<BackupUUID>\"
python rescue.py photos --source "C:\Users\<you>\AppData\Roaming\Apple Computer\MobileSync\Backup\<BackupUUID>\" --output "C:\Users\<you>\Desktop\Rescue" --format original
```

# Troubleshooting (for future scripts being built, and issues we are seeing)

## 🛠 Troubleshooting

| Problem | Likely cause | Fix |
|--------|--------------|-----|
| `Manifest.db` missing | Not pointed at correct Backup UUID folder | Double-check path — `Manifest.db` lives in the `<BackupUUID>` folder (not the parent MobileSync folder). |
| Permission denied | macOS Full Disk Access not granted | System Settings → Privacy & Security → Full Disk Access → add Terminal or IDE. |
| Encrypted DBs / unreadable Keychain | Backup is encrypted and password not supplied | Re-run with `--password "your-backup-password"` or use the Finder to decrypt/export first. |
| Attachments missing (photos/large videos) | Attachments were stored in iCloud, not in the local backup | Check iCloud export or ask user to provide a device-level extraction or iCloud export. |
| HEIC images not opening | HEIC conversion library missing | `pip install pyheif pillow` and/or install `libheif` on the host OS. |
| Very large exports | Disk space or memory constraints | Ensure plenty of disk space; run `contacts`/`messages`/`photos` separately and stream outputs. |

---

## 🧰 Tools Folder

Everything modular is planned here.
Each script under /tools is standalone, chainable, and importable from the main CLI.

Planned contents:|
| File                    | Description                                                                       |
| ----------------------- | --------------------------------------------------------------------------------- |
| `manifest_parser.py`    | Parses and indexes `Manifest.db` + file hashes                                    |
| `contact_parser.py`     | Extracts AddressBook / ContactsV2 databases                                       |
| `message_parser.py`     | Handles SMS + iMessage databases                                                  |
| `note_parser.py`        | Decodes Notes SQLite archives                                                     |
| `calendar_parser.py`    | Reads and exports calendar events                                                 |
| `photo_recovery.py`     | Locates and restores image metadata + thumbnails                                  |
| `password_rescue.py`    | (Planned) Detects Keychain backups and parses password hints / tokens             |
| `imessage_rebuilder.py` | (Planned) Deep iMessage thread reconstruction — attachments, metadata, timestamps |
| `utils.py`              | Shared helper functions for encoding, hashing, timestamp formatting, etc.         |
| `report_generator.py`   | Builds HTML/JSON summaries from exported artifacts                                |

---

```python
python rescue.py analyze ~/Backups/iPhone15/
python rescue.py contacts --source ~/Backups/iPhone15/ --output ~/Desktop/Rescue --format csv
python rescue.py messages --source ~/Backups/iPhone15/ --output ~/Desktop/Rescue --format html
python rescue.py report --source ~/Desktop/Rescue --output ~/Desktop/Rescue/summary.html
```

---

## 🔮 Roadmap

We’re expanding the toolkit to cover deeper layers of iOS data.
Here’s what’s planned (and realistically achievable):
| Module              | Status | Description                                                                 |
| ------------------- | ------ | --------------------------------------------------------------------------- |
| **Contacts Rescue** | ✅      | Complete and stable                                                         |
| **Messages Rescue** | 🧩     | Stable, refining iMessage parsing                                           |
| **Notes Rescue**    | 🔜     | Next up — SQLite and plist hybrid recovery                                  |
| **Photos Rescue**   | 🔜     | Metadata + thumbnail reconstruction from `MediaDomain`                      |
| **Password Rescue** | ⚠️     | Feasibility research — Keychain.db parsing requires decrypted backup access |
| **Calendar Rescue** | 🧪     | EventKit and CalDAV export from plist databases                             |
| **iMessage Rescue** | 🚧     | Early research stage — cross-device merge support coming soon               |

---

## 🩶 License

MIT — because data recovery shouldn’t be proprietary, nor should it cost so much/  Except for those hardware guys swapping platters in 3.5" HDD - you dudes are legends!



