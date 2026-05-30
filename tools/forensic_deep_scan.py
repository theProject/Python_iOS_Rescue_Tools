from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tools.forensic_common import file_size_mb, guess_app_from_record_domain, is_likely_directory_record, is_sqlite_file, safe_output_path, sha256_file
from tools.forensic_models import ExtractedArtifact, ManifestRecord
from tools.forensic_reports import write_cards_html, write_csv, write_json, write_table_html
from tools.forensic_teams import inspect_sqlite_keywords, scan_text_keywords, sqlite_sidecar_type


DEFAULT_DEEP_KEYWORDS = ["Tesla", "Julio", "Jake", "Monitor", "ADHD", "Bikrom"]
DEEP_DOMAIN_PREFIXES = ("AppDomain-", "AppDomainGroup-", "SysSharedContainerDomain-", "PluginKitPlugin-")
DEEP_PATH_RE = re.compile(r"(cache|caches|database|databases|sqlite|realm|leveldb|indexeddb|storage|logs?|preferences|application support|documents|tmp|metadata)", re.I)
DEEP_EXTS = {".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm", ".sqlite-wal", ".sqlite-shm", ".realm", ".json", ".plist", ".txt", ".log", ".xml", ".html", ".htm", ".ldb", ".sst"}


def is_deep_candidate(record: ManifestRecord) -> bool:
    if not record.domain.startswith(DEEP_DOMAIN_PREFIXES):
        return False
    suffix = Path(record.relative_path).suffix.lower()
    return suffix in DEEP_EXTS or bool(DEEP_PATH_RE.search(record.relative_path))


def run_deep_scan(
    records: list[ManifestRecord],
    extractor: Any,
    output: Path,
    keywords: list[str],
    max_file_mb: int,
    include_large: bool,
    text_limit_mb: int,
    sqlite_row_limit: int,
    export_context: int,
    warnings: list[str],
) -> dict[str, Any]:
    outdir = output / "deep_scan"
    extracted_dir = outdir / "extracted_files"
    sample_dir = outdir / "sqlite_samples"
    sample_dir.mkdir(parents=True, exist_ok=True)
    candidates = [r for r in records if is_deep_candidate(r)]
    artifacts: list[ExtractedArtifact] = []
    candidate_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    extracted_rows: list[dict[str, Any]] = []
    sqlite_db_rows: list[dict[str, Any]] = []
    sqlite_table_rows: list[dict[str, Any]] = []
    all_hits: list[dict[str, Any]] = []
    sqlite_hits: list[dict[str, Any]] = []
    text_hits: list[dict[str, Any]] = []
    sqlite_count = 0
    text_count = 0
    directory_skipped = 0
    extraction_failures = 0
    for record in candidates:
        candidate_rows.append({"file_id": record.file_id, "domain": record.domain, "relative_path": record.relative_path, "logical_path": record.logical_path, "app_guess": guess_app_from_record_domain(record.domain)})
        dest = safe_output_path(extracted_dir, record.domain, record.relative_path)
        if is_likely_directory_record(record.domain, record.relative_path, record.metadata):
            directory_skipped += 1
            skipped_rows.append({"file_id": record.file_id, "logical_path": record.logical_path, "reason": "directory_record_not_extractable", "size_mb": None})
            artifacts.append(ExtractedArtifact("deep_scan", record.file_id, record.domain, record.relative_path, record.logical_path, None, str(dest), None, None, 0, extractor.is_encrypted(), False, True, "directory_record_not_extractable"))
            continue
        source_obj = extractor.source_object_path(record.file_id)
        size_mb = file_size_mb(source_obj) if source_obj and source_obj.exists() else None
        if size_mb is not None and size_mb > max_file_mb and not include_large:
            row = {"file_id": record.file_id, "logical_path": record.logical_path, "reason": f"Skipped by --max-deep-file-mb ({max_file_mb})", "size_mb": size_mb}
            skipped_rows.append(row)
            artifacts.append(ExtractedArtifact("deep_scan", record.file_id, record.domain, record.relative_path, record.logical_path, str(source_obj), str(dest), sha256_file(source_obj), None, 0, extractor.is_encrypted(), False, True, row["reason"]))
            continue
        artifact = extractor.extract_record(record, dest, "deep_scan")
        artifacts.append(artifact)
        if not artifact.extracted:
            extraction_failures += 1
            skipped_rows.append({"file_id": record.file_id, "logical_path": record.logical_path, "reason": artifact.skip_reason, "size_mb": size_mb})
            continue
        actual_path = Path(artifact.output_path)
        sidecar = sqlite_sidecar_type(actual_path)
        if size_mb is None:
            size_note = "Pre-extraction source size was unknown; size policy could not be evaluated until after extraction."
            artifact.notes = f"{artifact.notes} {size_note}".strip()
        extracted_rows.append({"file_id": record.file_id, "logical_path": record.logical_path, "extracted_path": str(actual_path), "sha256": artifact.output_sha256, "app_guess": guess_app_from_record_domain(record.domain), "artifact_type": sidecar or "candidate", "pre_extraction_size_mb": size_mb, "output_size": artifact.output_size, "notes": artifact.notes})
        try:
            if sidecar:
                skipped_rows.append({"file_id": record.file_id, "logical_path": record.logical_path, "reason": f"{sidecar}_sidecar_not_text_scanned", "size_mb": size_mb})
            elif is_sqlite_file(actual_path):
                sqlite_count += 1
                sqlite_db_rows.append({"database": str(actual_path), "logical_path": record.logical_path, "sha256": artifact.output_sha256, "app_guess": guess_app_from_record_domain(record.domain)})
                tables, _, hits = inspect_sqlite_keywords(actual_path, keywords, sqlite_row_limit, sample_dir, record, "deep_sqlite", context=export_context)
                sqlite_table_rows.extend(tables)
                rows = [h.__dict__ for h in hits]
                sqlite_hits.extend(rows)
                all_hits.extend(rows)
            else:
                text_count += 1
                hits = scan_text_keywords(actual_path, record, keywords, text_limit_mb, "deep_text", context=export_context)
                rows = [h.__dict__ for h in hits]
                text_hits.extend(rows)
                all_hits.extend(rows)
        except Exception as exc:
            message = f"Could not inspect deep scan candidate {record.logical_path}: {exc}"
            warnings.append(message)
            skipped_rows.append({"file_id": record.file_id, "logical_path": record.logical_path, "reason": message, "size_mb": size_mb})
    write_csv(outdir / "deep_candidate_files.csv", candidate_rows)
    write_json(outdir / "deep_candidate_files.json", candidate_rows)
    write_csv(outdir / "deep_extracted_manifest.csv", extracted_rows)
    write_json(outdir / "deep_extracted_manifest.json", extracted_rows)
    write_csv(outdir / "deep_keyword_hits.csv", all_hits)
    write_json(outdir / "deep_keyword_hits.json", all_hits)
    write_cards_html(outdir / "deep_keyword_hits.html", "Deep Scan Keyword Hits", all_hits)
    write_csv(outdir / "deep_sqlite_databases.csv", sqlite_db_rows)
    write_csv(outdir / "deep_sqlite_tables.csv", sqlite_table_rows)
    write_csv(outdir / "deep_text_hits.csv", text_hits)
    write_csv(outdir / "deep_sqlite_hits.csv", sqlite_hits)
    write_csv(outdir / "skipped_files.csv", skipped_rows)
    write_json(outdir / "skipped_files.json", skipped_rows)
    summary = {
        "candidate_files": len(candidates),
        "extracted_files": len(extracted_rows),
        "skipped_files": len(skipped_rows),
        "sqlite_databases": sqlite_count,
        "text_files": text_count,
        "keyword_hits": len(all_hits),
        "directory_records_skipped": directory_skipped,
        "extraction_failures": extraction_failures,
        "keywords": keywords,
        "sqlite_row_limit": sqlite_row_limit,
        "sqlite_row_limit_note": "unlimited" if sqlite_row_limit <= 0 else str(sqlite_row_limit),
        "export_context": export_context,
    }
    write_json(outdir / "deep_scan_summary.json", summary)
    write_table_html(outdir / "deep_scan_summary.html", "Deep Scan Summary", [summary])
    return {**summary, "artifacts": artifacts}
