import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from ingestion.models import FireHotspotBatch

# Repo-level data folder; app.py reads the same file.
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "data" / "firms_hotspots.json"


def write_batch(batch: FireHotspotBatch, output_path: str | Path = DEFAULT_OUTPUT) -> Path:
    """Write atomically so the app never reads a half-written file."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=destination.parent,
                            prefix=f".{destination.name}.", delete=False) as temporary:
        json.dump(batch.to_dict(), temporary, indent=2)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, destination)
    return destination
