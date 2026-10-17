# GoEZ backend

## Smoke dispersion service

The smoke model estimates a downwind trajectory, an expanding plume polygon,
relative PM2.5 impact, and affected population locations. It is a decision
support approximation and is not an official emergency or air-quality forecast.

## Local setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`, with interactive
documentation at `http://127.0.0.1:8000/docs`.

### Endpoint

`POST /api/v1/smoke/forecast`

The request accepts a fire, weather conditions, forecast duration, and optional
population locations. Wind direction follows the meteorological convention
(the direction the wind comes from); the model transports smoke in the
opposite direction.
