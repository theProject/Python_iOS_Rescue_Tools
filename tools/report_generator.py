import os, json, glob
from utils import ensure_dir, write_html_table, write_json, log_ok

def build_report(source_exports_root: str, out_html_path: str):
    """
    source_exports_root should be the parent directory containing exported modules
    (e.g., .../Rescue with contacts/, messages/, photos/, etc inside).
    """
    summary = []
    for folder in sorted(os.listdir(source_exports_root)):
        full = os.path.join(source_exports_root, folder)
        if not os.path.isdir(full): continue
        # Count rows if a JSON exists
        count = None
        j = os.path.join(full, f"{folder}.json")
        if not os.path.exists(j):
            # try first json file
            import glob
            js = glob.glob(os.path.join(full, "*.json"))
            if js:
                j = js[0]
        if os.path.exists(j):
            try:
                data = json.load(open(j, "r", encoding="utf-8"))
                count = len(data) if isinstance(data, list) else 1
            except Exception:
                pass
        summary.append({"module": folder, "items": count if count is not None else "—", "path": full})
    write_json(out_html_path.replace(".html",".json"), summary)
    write_html_table(out_html_path, "Rescue Summary", summary)
    log_ok(f"Summary built for {len(summary)} modules")
    return summary