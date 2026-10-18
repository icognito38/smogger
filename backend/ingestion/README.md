# NASA FIRMS global hotspot ingestion

This module collects one day of global fire hotspots from the
`VIIRS_SNPP_NRT` source, checks data availability, and writes a standardized
JSON batch for the model, smoke-impact, and frontend modules.

## Configuration

Map keys must be supplied at runtime and must not be committed. The collector
loads `backend\ingestion\.env` automatically:

```text
FIRMS_MAP_KEYS1='key1'
FIRMS_MAP_KEYS2='key2'
FIRMS_MAP_KEYS3='key3'
FIRMS_MAP_KEYS4='key4'
FIRMS_MAP_KEYS5='key5'
```

Keys are attempted in numeric order. Environment variables take precedence
over values in `.env`. For compatibility, a single comma-separated
`FIRMS_MAP_KEYS` variable is also supported. If a key fails either operation,
the next key is tried. Error messages identify the key position, never the key
value.

Do not place the supplied keys in source code, notebooks, JSON, Git history,
or command output. Store them in a protected environment variable or secret
manager on the machine that runs the scheduled collector.

## Endpoints used

```text
GET https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv/{MAP_KEY}/VIIRS_SNPP_NRT
GET https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/world/1/{max_date}
```

Step 1 reads `max_date` from the availability CSV; a key that errors or returns no dated row is skipped.
Step 2 streams the area CSV for that date row by row (the global file is usually 50,000+ rows).

## Standardized output

Default output: `data/firms_hotspots.json` at the repository root (read by `app.py`). Each record keeps
only the five fields the platform uses:

```json
{
  "schema_version": "2.0",
  "source": "VIIRS_SNPP_NRT",
  "region": "world",
  "day_range": 1,
  "date": "2026-10-17",
  "retrieved_at_utc": "2026-10-18T02:46:53+00:00",
  "count": 56212,
  "data_availability": [{"source": "VIIRS_SNPP_NRT", "available": true, "status_code": 200,
                         "min_date": "2026-07-01", "max_date": "2026-10-17", "checked_at_utc": "..."}],
  "hotspots": [
    {"latitude": 19.39828, "longitude": -155.29004, "date": "2026-10-17", "time": "00:05", "confidence": "n"}
  ]
}
```

`confidence` is the FIRMS value (`l`, `n`, `h` for VIIRS); times are UTC.

## Running

Install the dependency from the backend directory:

```powershell
python -m pip install -r requirements-ingestion.txt
```

Fetch immediately:

```powershell
python -m ingestion.cli --once
```

Run continuously (fetch now if the file is missing or older than 24 h, then every 24 h):

```powershell
python -m ingestion.cli
```

`app.py` starts the same 24-hour loop in a background thread when keys are configured, so a separate
collector process is optional.
