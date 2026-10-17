# NASA FIRMS global hotspot ingestion

This module collects one day of global fire hotspots from the
`VIIRS_SNPP_NRT` source and writes a standardized JSON batch for the model,
smoke-impact, and frontend modules.

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
GET https://firms.modaps.eosdis.nasa.gov/api/data_availability/html/{MAP_KEY}/VIIRS_SNPP_NRT
GET https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/world/1
```

The source endpoint is the CSV form of the requested global area endpoint.
The requested HTML form is suitable for inspection but CSV is the stable
machine-readable format.

## Standardized output

The default output is `data/firms_global_latest.json`:

```json
{
  "schema_version": "1.0",
  "source": "VIIRS_SNPP_NRT",
  "region": "world",
  "day_range": 1,
  "retrieved_at_utc": "2026-10-17T00:00:00+00:00",
  "hotspots": [
    {
      "fire_id": "firms-...",
      "latitude": 19.39828,
      "longitude": -155.29004,
      "confidence": "n",
      "confidence_score": 50.0,
      "acquired_at_utc": "2026-10-17T00:05:00+00:00",
      "satellite": "N",
      "instrument": "VIIRS",
      "source": "VIIRS_SNPP_NRT",
      "source_day_range": 1,
      "brightness_temperature_k": 332.19,
      "fire_radiative_power_mw": 59.85,
      "daynight": "D"
    }
  ]
}
```

`confidence` preserves the FIRMS source value (`l`, `n`, or `h` when supplied)
and `confidence_score` provides a numeric downstream-friendly mapping:
low = 25, nominal = 50, high = 90. Coordinates are decimal degrees.
Acquisition timestamps are normalized to UTC because FIRMS acquisition times
are UTC. The source day range is retained for traceability.

## Running

Install the dependency from the backend directory:

```powershell
python -m pip install requests
```

Fetch immediately:

```powershell
python -m ingestion.cli --once
```

Run continuously, fetching at local midnight in the `Europe/London` timezone
(00:00 during BST and GMT):

```powershell
python -m ingestion.cli
```

The `--once` mode is recommended for testing and scheduled production jobs.
The daemon mode waits until the next local midnight and then repeats every
24-hour calendar boundary. It does not contain API keys or require the
prediction model.
