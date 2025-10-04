import json
import os
from datetime import datetime
from pathlib import Path

# === RÉPERTOIRE DU PROJET ===
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_DIR = PROJECT_ROOT / "overall_context" / "logs"
LOG_FILE = LOG_DIR / "backup_restore_events.jsonl"


def log_event(operation: str, zone: str, status: str, details: dict, timestamp: str = None):
    from datetime import datetime

    if timestamp is None:
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")

    event = {
        "operation": operation,
        "zone": zone,
        "status": status,
        "timestamp": timestamp,
        "details": details,
    }

    # Use confined logs directory and sanitize zone to avoid path traversal
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    safe_zone = "".join(c for c in (zone or "") if c.isalnum() or c in ("_", "-")) or "zone"
    log_file_path = LOG_DIR / f"{safe_zone}_log.json"

    try:
        if log_file_path.exists():
            data = json.loads(log_file_path.read_text(encoding="utf-8"))
        else:
            data = []

        data.append(event)

        log_file_path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
    except Exception as e:
        print(f"❌ Erreur lors de l'enregistrement du log : {e}")
