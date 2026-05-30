import csv
import json
import plistlib
import sqlite3
from pathlib import Path

from tools.forensic_backup import run_forensic_triage


def _write_sms_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT)")
    conn.execute(
        "CREATE TABLE message (ROWID INTEGER PRIMARY KEY, guid TEXT, date INTEGER, is_from_me INTEGER, handle_id INTEGER, text TEXT, service TEXT)"
    )
    conn.execute("INSERT INTO handle VALUES (1, '+15551234567')")
    conn.execute("INSERT INTO message VALUES (1, 'sms-guid', 700000000, 0, 1, 'Forensic SMS fixture', 'iMessage')")
    conn.commit()
    conn.close()


def _write_app_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE cache_items (body TEXT)")
    conn.execute("INSERT INTO cache_items VALUES ('Tesla keyword appears in app cache')")
    conn.commit()
    conn.close()


def test_forensics_e2e_fake_mobilesync_backup(tmp_path):
    backup = tmp_path / "BACKUP_UUID"
    backup.mkdir()
    (backup / "aa").mkdir()
    (backup / "bb").mkdir()

    with (backup / "Manifest.plist").open("wb") as f:
        plistlib.dump({"IsEncrypted": False, "Version": "fixture"}, f)
    with (backup / "Info.plist").open("wb") as f:
        plistlib.dump({"Display Name": "Fixture iPhone", "Product Type": "iPhone", "Product Version": "17.0"}, f)

    _write_sms_db(backup / "aa" / "aaaaaaaa")
    _write_app_db(backup / "bb" / "bbbbbbbb")

    conn = sqlite3.connect(backup / "Manifest.db")
    conn.execute("CREATE TABLE Files (fileID TEXT, domain TEXT, relativePath TEXT, flags INTEGER, file BLOB)")
    conn.execute("INSERT INTO Files VALUES (?, ?, ?, 0, NULL)", ("aaaaaaaa", "HomeDomain", "Library/SMS/sms.db"))
    conn.execute(
        "INSERT INTO Files VALUES (?, ?, ?, 0, NULL)",
        ("bbbbbbbb", "AppDomain-com.teslamotors.TeslaApp", "Library/Caches/cache.sqlite"),
    )
    conn.commit()
    conn.close()

    output = tmp_path / "case-output"
    args = type(
        "Args",
        (),
        {
            "source": str(backup),
            "output": str(output),
            "targets": ["sms", "teams"],
            "password_env": None,
            "password": None,
            "prompt_password": False,
            "no_attachments": False,
            "keyword": ["Tesla"],
            "sample_limit": 50,
            "max_teams_file_mb": 5,
            "include_large_teams_files": False,
            "deep_app_cache_scan": True,
            "deep_keyword": [],
            "max_deep_file_mb": 5,
            "include_large_deep_files": False,
            "deep_scan_text_limit_mb": 5,
            "deep_scan_sqlite_row_limit": 0,
            "deep_scan_export_context": 240,
            "write_timeline": True,
        },
    )()

    run_forensic_triage(args)

    assert (output / "case_summary.json").exists()
    assert (output / "evidence_manifest.csv").exists()
    assert (output / "sms" / "sms_messages.csv").exists()
    deep_hits = output / "deep_scan" / "deep_keyword_hits.csv"
    assert deep_hits.exists()
    assert "Tesla" in deep_hits.read_text(encoding="utf-8")
    assert (output / "review" / "high_signal_hits.csv").exists()
    assert "Tesla" in (output / "review" / "keyword_summary.csv").read_text(encoding="utf-8")


def test_deep_scan_relocates_file_directory_output_collision(tmp_path):
    backup = tmp_path / "BACKUP_UUID"
    backup.mkdir()
    (backup / "cc").mkdir()
    (backup / "dd").mkdir()

    with (backup / "Manifest.plist").open("wb") as f:
        plistlib.dump({"IsEncrypted": False, "Version": "fixture"}, f)

    (backup / "cc" / "cccccccc").write_text("plain user cache file", encoding="utf-8")
    _write_app_db(backup / "dd" / "dddddddd")

    conn = sqlite3.connect(backup / "Manifest.db")
    conn.execute("CREATE TABLE Files (fileID TEXT, domain TEXT, relativePath TEXT, flags INTEGER, file BLOB)")
    conn.execute(
        "INSERT INTO Files VALUES (?, ?, ?, 0, NULL)",
        ("cccccccc", "AppDomain-test", "Documents/user"),
    )
    conn.execute(
        "INSERT INTO Files VALUES (?, ?, ?, 0, NULL)",
        ("dddddddd", "AppDomain-test", "Documents/user/profile.sqlite"),
    )
    conn.commit()
    conn.close()

    output = tmp_path / "case-output"
    args = type(
        "Args",
        (),
        {
            "source": str(backup),
            "output": str(output),
            "targets": ["teams"],
            "password_env": None,
            "password": None,
            "prompt_password": False,
            "no_attachments": False,
            "keyword": [],
            "sample_limit": 50,
            "max_teams_file_mb": 5,
            "include_large_teams_files": False,
            "deep_app_cache_scan": True,
            "deep_keyword": [],
            "max_deep_file_mb": 5,
            "include_large_deep_files": False,
            "deep_scan_text_limit_mb": 5,
            "deep_scan_sqlite_row_limit": 0,
            "deep_scan_export_context": 240,
            "write_timeline": False,
        },
    )()

    run_forensic_triage(args)

    with (output / "evidence_manifest.json").open("r", encoding="utf-8") as f:
        artifacts = json.load(f)
    collision_note = "Preferred output path collided with an existing file/directory; artefact relocated to collision-safe path."
    collision_artifacts = [a for a in artifacts if collision_note in a.get("notes", "")]
    assert len([a for a in artifacts if a["label"] == "deep_scan" and a["extracted"]]) == 2
    assert collision_artifacts
    assert all(Path(a["output_path"]).exists() for a in artifacts if a["label"] == "deep_scan")

    with (output / "deep_scan" / "deep_extracted_manifest.csv").open("r", newline="", encoding="utf-8") as f:
        extracted_rows = list(csv.DictReader(f))
    reported_collision_paths = [row["extracted_path"] for row in extracted_rows if collision_note in row["notes"]]
    assert reported_collision_paths
    assert "_path_collisions" in reported_collision_paths[0]
    assert Path(reported_collision_paths[0]).exists()

    hits = (output / "deep_scan" / "deep_keyword_hits.csv").read_text(encoding="utf-8")
    assert "Tesla" in hits
    assert "_path_collisions" in hits
