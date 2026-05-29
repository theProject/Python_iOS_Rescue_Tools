import argparse
import sqlite3

from tools.forensic_backup import add_forensic_parser
from tools.forensic_deep_scan import DEFAULT_DEEP_KEYWORDS, is_deep_candidate
from tools.forensic_models import ManifestRecord
from tools.forensic_teams import inspect_sqlite_keywords, scan_text_keywords


def test_deep_candidate_detection():
    record = ManifestRecord("id", "AppDomain-com.teslamotors.TeslaApp", "Library/Application Support/cache/state.json")
    assert is_deep_candidate(record)


def test_keyword_search_in_raw_text(tmp_path):
    path = tmp_path / "state.log"
    path.write_text("Monitor keyword appears here", encoding="utf-8")
    record = ManifestRecord("id", "AppDomain-com.example.app", "Library/Logs/state.log")
    hits = scan_text_keywords(path, record, ["Monitor"])
    assert hits[0].keyword == "Monitor"


def test_deep_scan_export_context_parses_as_integer():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    add_forensic_parser(sub)
    args = parser.parse_args(["forensics", "--source", "/tmp/backup", "--deep-scan-export-context", "17"])
    assert args.deep_scan_export_context == 17
    assert isinstance(args.deep_scan_export_context, int)


def test_deep_scan_default_cli_values_are_forensic_complete():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    add_forensic_parser(sub)
    args = parser.parse_args(["forensics", "--source", "/tmp/backup"])
    assert args.deep_scan_export_context == 240
    assert args.deep_scan_sqlite_row_limit == 0


def test_deep_scan_default_keywords_still_include_required_terms():
    assert {"Tesla", "Julio", "Jake", "Monitor", "ADHD", "Bikrom"}.issubset(set(DEFAULT_DEEP_KEYWORDS))


def _keyword_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE cache_items (body TEXT)")
    conn.execute("INSERT INTO cache_items VALUES ('Tesla first row')")
    conn.execute("INSERT INTO cache_items VALUES ('Tesla second row')")
    conn.commit()
    conn.close()


def test_sqlite_row_limit_zero_scans_all_rows(tmp_path):
    db = tmp_path / "cache.sqlite"
    _keyword_db(db)
    record = ManifestRecord("id", "AppDomain-com.example.app", "Library/Caches/cache.sqlite")
    _, _, hits = inspect_sqlite_keywords(db, ["Tesla"], 0, tmp_path / "samples", record)
    assert len(hits) == 2


def test_sqlite_row_limit_one_scans_only_one_row(tmp_path):
    db = tmp_path / "cache.sqlite"
    _keyword_db(db)
    record = ManifestRecord("id", "AppDomain-com.example.app", "Library/Caches/cache.sqlite")
    _, _, hits = inspect_sqlite_keywords(db, ["Tesla"], 1, tmp_path / "samples", record)
    assert len(hits) == 1


def test_deep_scan_hit_snippets_respect_configured_context(tmp_path):
    path = tmp_path / "state.log"
    path.write_text("AAAAATeslaBBBBB", encoding="utf-8")
    record = ManifestRecord("id", "AppDomain-com.example.app", "Library/Logs/state.log")
    hits = scan_text_keywords(path, record, ["Tesla"], context=2)
    assert hits[0].snippet == "AATeslaBB"
