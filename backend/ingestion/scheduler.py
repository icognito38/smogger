import logging
import time
from pathlib import Path

from ingestion.client import FirmsClient
from ingestion.models import FireHotspotBatch
from ingestion.storage import DEFAULT_OUTPUT, write_batch

LOGGER = logging.getLogger(__name__)
REFRESH_SECONDS = 24 * 60 * 60


def run_once(client: FirmsClient, output_path: str | Path = DEFAULT_OUTPUT) -> FireHotspotBatch:
    batch = client.fetch_global_hotspots()
    write_batch(batch, output_path)
    return batch


def is_stale(output_path: str | Path = DEFAULT_OUTPUT, max_age_seconds: float = REFRESH_SECONDS) -> bool:
    path = Path(output_path)
    return not path.is_file() or time.time() - path.stat().st_mtime >= max_age_seconds


def run_every_24h(client: FirmsClient, output_path: str | Path = DEFAULT_OUTPUT,
                  sleep=time.sleep) -> None:
    """Fetch now (unless the file is fresh), then every 24 hours. A failed fetch keeps the old file."""
    while True:
        if is_stale(output_path):
            try:
                batch = run_once(client, output_path)
                LOGGER.info("Saved %d hotspots to %s", len(batch.hotspots), output_path)
            except Exception:
                LOGGER.exception("FIRMS refresh failed; keeping the previous file")
        sleep(REFRESH_SECONDS)
