# GoEZ backend

## Smoke impact service

This service consumes the six-hour city trajectory produced by the prediction
branch. It does not calculate a competing trajectory. It estimates a
percentage smoke-risk score, confidence, relative PM2.5 impact, exposure
duration, and a health advisory for each predicted city.

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

`POST /api/v1/smoke/impact`

The request accepts fire context and predicted cities. The prediction branch
owns the trajectory, arrival hour, distance, and path probability. This branch
only scores the supplied city predictions.

Example request:

```json
{
  "fire": {
    "size_hectares": 120,
    "intensity": 0.8
  },
  "cities": [
    {
      "name": "City A",
      "latitude": 34.2,
      "longitude": -118.1,
      "arrival_hour": 2,
      "distance_from_fire_km": 24,
      "path_probability": 0.72
    }
  ],
  "forecast_hours": 6
}
```
