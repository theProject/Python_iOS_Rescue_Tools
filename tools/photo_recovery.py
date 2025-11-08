import os
from pathlib import Path
from typing import List, Dict
from utils import ensure_dir, write_csv, write_json, write_html_table, log_info, log_ok, log_warn, hash_file
from settings import PHOTO_EXTS

try:
    from PIL import Image
    PIL_OK = True
except Exception:
    PIL_OK = False

try:
    import exifread
    EXIF_OK = True
except Exception:
    EXIF_OK = False

def _gather_media(source: str) -> List[str]:
    hits = []
    for dirpath, _, filenames in os.walk(source):
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in PHOTO_EXTS:
                hits.append(os.path.join(dirpath, fn))
    return hits

def _extract_exif(path: str) -> Dict:
    if not EXIF_OK:
        return {}
    try:
        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=False)
        out = {}
        for k in ("Image Make","Image Model","EXIF DateTimeOriginal","GPS GPSLatitude","GPS GPSLongitude"):
            if k in tags:
                out[k] = str(tags[k])
        return out
    except Exception:
        return {}

def export_photos(source: str, outdir: str, convert_heic: bool = False):
    ensure_dir(outdir)
    media = _gather_media(source)
    rows = []
    gallery_dir = os.path.join(outdir, "original")
    ensure_dir(gallery_dir)
    for i, src in enumerate(media, 1):
        relname = os.path.basename(src)
        dst = os.path.join(gallery_dir, relname)
        try:
            hashv = hash_file(src)
        except Exception:
            hashv = ""
        # Copy file
        try:
            from utils import copy_file
            copy_file(src, dst)
        except Exception as e:
            log_warn(f"Copy failed for {src}: {e}")
            continue
        meta = _extract_exif(dst)
        rows.append({"filename": relname, "sha256": hashv, **meta})
    write_csv(os.path.join(outdir, "photos.csv"), rows)
    write_json(os.path.join(outdir, "photos.json"), rows)
    write_html_table(os.path.join(outdir, "gallery.html"), "Photos (originals)", rows[:2000])
    log_ok(f"Photos exported: {len(rows)}")
    return rows