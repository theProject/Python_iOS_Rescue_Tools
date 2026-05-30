from tools.forensic_common import redact_secrets, snippet_quality_fields
from tools.forensic_models import ManifestRecord
from tools.forensic_teams import scan_text_keywords


def test_redaction_of_tokens():
    text = "access_token: abcdefghijklmnop visible"
    redacted = redact_secrets(text)
    assert "abcdefghijklmnop" not in redacted
    assert "[REDACTED]" in redacted


def test_snippet_quality_removes_control_characters_and_flags_binary():
    quality = snippet_quality_fields("start\x00Tesla\x01end", "binary_text_fragment")
    assert "\x00" not in quality["clean_snippet"]
    assert "\x01" not in quality["clean_snippet"]
    assert "Tesla" in quality["clean_snippet"]
    assert quality["control_char_count"] == 2
    assert quality["printable_ratio"] < 1.0
    assert quality["binary_fragment"] is True
    assert quality["confidence"] in {"medium", "low"}


def test_scan_text_hits_include_clean_snippet_quality_fields(tmp_path):
    path = tmp_path / "mixed.bin"
    path.write_bytes(b"\x00\x01Tesla marker in binary-ish text\x02")
    record = ManifestRecord("id", "AppDomain-com.example.app", "Library/Caches/mixed.bin")

    hits = scan_text_keywords(path, record, ["Tesla"])

    assert len(hits) == 1
    assert hits[0].clean_snippet
    assert "Tesla" in hits[0].clean_snippet
    assert hits[0].binary_fragment is True
