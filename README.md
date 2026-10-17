# IBM-Z-GoEZ
Group GoEZ's repository for IBM Z datathon 2026!!!!

yapathon section
----------------------------------------------------------------------------
backend

## API branch: NASA FIRMS hotspot ingestion

The `API` branch contains a standalone ingestion module under
`backend/ingestion`. It fetches one day of global `VIIRS_SNPP_NRT` hotspots,
rotates through `FIRMS_MAP_KEYS` in order when a key fails, and writes the
standardized JSON batch consumed by downstream model and frontend modules.

See `backend/ingestion/README.md` for the schema, configuration, scheduling,
and integration contract. API keys must be supplied through the environment;
they are never stored in the repository.
