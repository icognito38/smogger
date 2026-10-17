import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from ingestion.models import FireHotspotBatch


def write_batch(batch: FireHotspotBatch, output_path: str | Path) -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        delete=False,
    ) as temporary:
        json.dump(batch.to_dict(), temporary, indent=2)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, destination)
    return destination
