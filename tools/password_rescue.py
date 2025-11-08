import os
from utils import log_info, log_warn, log_ok

def probe_password_artifacts(source: str):
    """
    Research-only: we do NOT attempt to decrypt Keychain here.
    We only report if likely keychain backups or hints are present.
    """
    hits = []
    candidates = ["keychain-backup.plist", "Keychain-2.db", "keychain-2.db"]
    for root, _, files in os.walk(source):
        for cand in candidates:
            if cand in files:
                hits.append(os.path.join(root, cand))
    if hits:
        log_ok(f"Potential keychain artifacts detected: {len(hits)} files")
    else:
        log_warn("No obvious keychain backup artifacts detected in this source.")
    return hits