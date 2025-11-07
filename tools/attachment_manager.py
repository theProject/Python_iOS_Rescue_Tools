import os, shutil
from pathlib import Path
from typing import Optional
from utils import ensure_dir, log_info, log_warn, log_ok

def safe_copy_by_basename(source_root: str, target_basename: str, dest_root: str) -> Optional[str]:
    """
    Fallback strategy: walk the backup tree and copy the first file that matches the basename
    (sms.db often stores absolute paths that don't exist within the backup folder structure).
    """
    for dirpath, _, filenames in os.walk(source_root):
        for fn in filenames:
            if fn == target_basename:
                src = os.path.join(dirpath, fn)
                rel = os.path.relpath(src, start=source_root)
                dst = os.path.join(dest_root, rel)
                ensure_dir(os.path.dirname(dst))
                shutil.copy2(src, dst)
                return dst
    return None