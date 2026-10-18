import argparse
import logging

from ingestion.client import FirmsClient
from ingestion.config import FirmsConfig
from ingestion.scheduler import run_every_24h, run_once
from ingestion.storage import DEFAULT_OUTPUT


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect global NASA FIRMS hotspots.")
    parser.add_argument("--once", action="store_true", help="Fetch immediately and exit.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="JSON output path.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    client = FirmsClient(FirmsConfig.from_environment())
    if args.once:
        batch = run_once(client, args.output)
        print(f"Saved {len(batch.hotspots)} hotspots for {batch.date} to {args.output}")
        return
    run_every_24h(client, args.output)


if __name__ == "__main__":
    main()
