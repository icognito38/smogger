import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ingestion.client import FirmsClient
from ingestion.models import FireHotspotBatch
from ingestion.storage import write_batch

LONDON_ZONE = ZoneInfo("Europe/London")


def next_midnight(now: datetime | None = None) -> datetime:
    current = now or datetime.now(LONDON_ZONE)
    local = current.astimezone(LONDON_ZONE)
    tomorrow = local.date() + timedelta(days=1)
    return datetime.combine(tomorrow, datetime.min.time(), tzinfo=LONDON_ZONE)


def run_once(client: FirmsClient, output_path: str) -> FireHotspotBatch:
    batch = client.fetch_global_hotspots()
    write_batch(batch, output_path)
    return batch


def run_daily(
    client: FirmsClient,
    output_path: str,
    sleep_seconds: int = 30,
) -> None:
    while True:
        scheduled_for = next_midnight()
        while datetime.now(LONDON_ZONE) < scheduled_for:
            time.sleep(sleep_seconds)
        run_once(client, output_path)
