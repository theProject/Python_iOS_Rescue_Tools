import csv
import plistlib
import sqlite3

from tools.forensic_backup import BackupExtractor
from tools.forensic_models import ManifestRecord
from tools.forensic_teams import inspect_sqlite_keywords, is_teams_candidate, run_teams_triage


def test_teams_candidate_detection():
    record = ManifestRecord("id", "AppDomainGroup-group.com.microsoft.skype.teams", "Library/Caches/chat.sqlite")
    assert is_teams_candidate(record)


def test_keyword_search_in_sqlite(tmp_path):
    db = tmp_path / "chat.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE messages (body TEXT)")
    conn.execute("INSERT INTO messages VALUES ('Chris mentioned Teams')")
    conn.commit()
    conn.close()
    record = ManifestRecord("id", "AppDomain-com.microsoft.skype.teams", "Library/Caches/chat.sqlite")
    _, _, hits = inspect_sqlite_keywords(db, ["Chris"], 100, tmp_path / "samples", record)
    assert len(hits) == 1
    assert hits[0].table == "messages"


def test_teams_triage_uses_actual_output_path_after_collision(tmp_path):
    backup = tmp_path / "BACKUP_UUID"
    backup.mkdir()
    (backup / "ee").mkdir()
    (backup / "ff").mkdir()
    with (backup / "Manifest.plist").open("wb") as f:
        plistlib.dump({"IsEncrypted": False}, f)
    (backup / "ee" / "eeeeeeee").write_text("teams cache marker", encoding="utf-8")
    db = backup / "ff" / "ffffffff"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE messages (body TEXT)")
    conn.execute("INSERT INTO messages VALUES ('Chris in relocated Teams sqlite')")
    conn.commit()
    conn.close()

    records = [
        ManifestRecord("eeeeeeee", "AppDomain-com.microsoft.skype.teams", "Library/Caches/user"),
        ManifestRecord("ffffffff", "AppDomain-com.microsoft.skype.teams", "Library/Caches/user/chat.sqlite"),
    ]
    output = tmp_path / "case-output"
    extractor = BackupExtractor(backup, output, None)
    warnings: list[str] = []

    result = run_teams_triage(records, extractor, output, ["Chris"], 50, 5, False, warnings)

    collision_note = "Preferred output path collided with an existing file/directory; artefact relocated to collision-safe path."
    assert result["candidate_files"] == 2
    assert len([a for a in result["artifacts"] if a.extracted]) == 2
    assert any(collision_note in a.notes for a in result["artifacts"])

    with (output / "teams" / "teams_candidate_files.csv").open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    collision_rows = [row for row in rows if collision_note in row["notes"]]
    assert collision_rows
    assert "_path_collisions" in collision_rows[0]["extracted_path"]

    hits = (output / "teams" / "teams_keyword_hits.csv").read_text(encoding="utf-8")
    assert "Chris" in hits
    assert "_path_collisions" in hits
