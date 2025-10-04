import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

LOGS_DIR = Path("embedding_logs")
MANIFEST_PATH = LOGS_DIR / "_manifest.json"
LOGS_DIR.mkdir(exist_ok=True)


def sha512_hash(filepath: Path) -> str:
    hasher = hashlib.sha512()
    with filepath.open("rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()


def log_vectorization_run(
    zone_id: str,
    mode: str,
    engine: str,
    source_file: Path,
    output_file: Path,
    vector_count: int,
    duration: float,
    status: str = "success",
    error: str = None,
    triggered_by: str = "user",
    agent: str = "Thomas",
):
    now = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
    log_filename = f"{now}__{zone_id}__{mode}.json"
    log_path = LOGS_DIR / log_filename

    hash_output = sha512_hash(output_file) if output_file.exists() else None

    log_data = {
        "zone_id": zone_id,
        "mode": mode,
        "engine": engine,
        "status": status,
        "vector_count": vector_count,
        "source_file": str(source_file),
        "output_file": str(output_file),
        "hash_output": hash_output,
        "duration_seconds": round(duration, 3),
        "created_at": now,
        "agent": agent,
        "triggered_by": triggered_by,
        "error": error,
        "notes": None,
    }

    # Write individual log
    log_path.write_text(json.dumps(log_data, indent=2, ensure_ascii=False))

    # Update _manifest
    manifest = []
    if MANIFEST_PATH.exists():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            manifest = []

    manifest.append(log_data)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"📌 Log enregistré : {log_path}")
