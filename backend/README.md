# GoEZ smoke-impact backend

## Purpose and ownership

This branch owns the **smoke-impact assessment layer**. It does not collect
live fire or weather data, train a trajectory model, calculate wind direction,
or create an alternative smoke path. Those responsibilities belong to the
other project branches.

The trajectory/model branch supplies a six-hour prediction for each city. This
branch consumes those predictions and adds user-facing impact information:

- A 0-100 smoke-risk percentage
- A rank ordering cities from highest to lowest smoke risk
- A risk category
- The model's predicted PM2.5 value
- A confidence percentage based on the supplied path probability
- Estimated exposure duration within the six-hour window
- A short health advisory

This separation prevents two branches from producing competing smoke
trajectories or competing PM2.5 forecasts.

## Runtime and language

The service is written in **Python** and uses:

- **FastAPI** for the HTTP API
- **Pydantic 2** for JSON parsing and input validation
- Python's standard library only for the impact calculation
- **Pytest** for automated tests

The service does not require a database or external API key. The prediction
model and live-data branches are upstream producers; this service receives
their normalized output as JSON.

## Endpoint

```text
POST /api/v1/smoke/impact
```

The endpoint accepts a trajectory prediction and returns a city-by-city
impact assessment. The endpoint does not return `wind_direction`,
`smoke_direction`, trajectory points, plume geometry, or a new path.

## Required input

The request must contain:

| Field | Type | Required | Meaning |
|---|---:|:---:|---|
| `cities` | array | Yes | At least one predicted city |
| `cities[].name` | string | Yes | City identifier |
| `cities[].latitude` | number | Yes | Decimal latitude, -90 to 90 |
| `cities[].longitude` | number | Yes | Decimal longitude, -180 to 180 |
| `cities[].arrival_hour` | integer | Yes | Expected arrival, 0 to 6 hours from now |
| `cities[].predicted_pm25_6h` or `Predicted_PM25_6h` | number | Yes | Teammate model's PM2.5 forecast in micrograms per cubic metre |
| `cities[].path_probability` | number | No | Probability from 0 to 1; defaults to 1 |
| `cities[].distance_from_fire_km` | number | One distance field required | Distance from fire in kilometres |
| `cities[].distance_from_fire_miles` | number | One distance field required | Notebook-compatible distance in miles |
| `forecast_hours` | integer | No | Forecast window; defaults to 6 and cannot exceed 6 |
| `fire` | object | No | Optional fire coordinates for display/context only |

The distance is not used to recalculate PM2.5 or trajectory. It is retained
for traceability and compatibility with the teammate's output. If the
notebook's `Distance_Miles` value is supplied, the integration layer should
rename it to `distance_from_fire_miles`; this service converts it to
kilometres using `1 mile = 1.609344 km`.

### Canonical integration payload

The preferred shared contract is:

```json
{
  "fire": {
    "latitude": 49.0,
    "longitude": -73.0
  },
  "cities": [
    {
      "name": "Montreal",
      "latitude": 45.5016,
      "longitude": -73.5672,
      "arrival_hour": 6,
      "distance_from_fire_km": 575.2,
      "path_probability": 0.76,
      "predicted_pm25_6h": 42.8
    }
  ],
  "forecast_hours": 6
}
```

The notebook uses `Predicted_PM25_6h` with capital letters. That exact field
name is accepted, as is the canonical Python/API name
`predicted_pm25_6h`. The notebook's `Distance_Miles` should be mapped to
`distance_from_fire_miles` before calling this endpoint.

## How the calculation works

For every supplied city, the service:

1. Reads `predicted_pm25_6h` directly from the upstream model.
2. Uses `path_probability` as the confidence input.
3. Converts PM2.5 to a presentation risk percentage:

   ```text
   concentration_factor = min(predicted_pm25_6h / 150, 1)
   risk_score_percent = concentration_factor × path_probability × 100
   ```

   `150 µg/m³` is the upper reference value for this hackathon score. It is
   not a claim that 150 is a universal maximum or an official regulatory
   threshold.

4. Copies the upstream PM2.5 value into `estimated_pm25`. The service does
   **not** estimate, decay, or replace that value.
5. Converts `path_probability` to `confidence_percent`.
6. Calculates exposure duration as:

   ```text
   forecast_hours - arrival_hour
   ```

   with a minimum of one hour.
7. Assigns a category based on the percentage score:

   | Score | Category |
   |---:|---|
   | 0-24.99 | `good` |
   | 25-49.99 | `moderate` |
   | 50-69.99 | `unhealthy_for_sensitive_groups` |
   | 70-89.99 | `unhealthy` |
   | 90-100 | `hazardous` |

These categories are application labels for the demo. The PM2.5 value and
health advice should be presented as an estimate and should not replace
official public-health or emergency guidance.

## Output

Successful responses have this shape:

```json
{
  "cities": [
    {
      "rank": 1,
      "name": "Montreal",
      "latitude": 45.5016,
      "longitude": -73.5672,
      "arrival_hour": 6,
      "estimated_pm25": 42.8,
      "risk_score_percent": 21.73,
      "risk_level": "good",
      "confidence_percent": 76.0,
      "exposure_duration_hours": 1,
      "health_advisory": "No special precautions are suggested based on this estimate."
    }
  ],
  "model_note": "Estimated smoke-impact scores based on the supplied city trajectory. They are not official air-quality measurements or emergency warnings."
}
```

The output intentionally contains no trajectory, wind direction, path
coordinates, or GeoJSON plume. The frontend should use the upstream
trajectory branch for map paths and this branch for city markers, risk
colouring, confidence, and advisories.

### Ranking behavior

The response's `cities` array is sorted from highest to lowest
`risk_score_percent`. Each city receives a one-based `rank`, where `1` is the
highest-priority city for smoke-impact response. If two cities have the same
risk score, the service uses predicted PM2.5 as a tie-breaker; if those values
also match, city name is used for deterministic ordering.

Ranking is performed only on the impact results supplied by this service. It
does not change the trajectory model's city order, arrival hours, or
predictions. The original upstream values remain attached to their city.

**Merge integration prompt:** When this branch is merged, the future
integrating LLM must preserve and verify this city-impact ranking feature.
Ensure that the final `/api/v1/smoke/impact` response sorts every city in
descending risk priority, assigns unique sequential one-based ranks (`1, 2,
3, ...`), and includes automated coverage proving that no two output cities
receive the same rank unless they are the same output record.

## Validation and errors

Invalid input receives FastAPI's standard HTTP `422` validation response.
Examples include:

- Missing `Predicted_PM25_6h` / `predicted_pm25_6h`
- Missing both distance fields
- Negative PM2.5
- `arrival_hour` outside 0-6
- `path_probability` outside 0-1
- Invalid latitude or longitude
- An empty `cities` list

The service does not silently substitute a missing PM2.5 forecast or invent a
trajectory. Upstream integration code must provide the required prediction.

## Local setup

From the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest tests -v
uvicorn app.main:app --reload
```

Interactive API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

The health check is:

```text
GET /health
```

## Example PowerShell request

```powershell
$body = @{
    fire = @{
        latitude = 49.0
        longitude = -73.0
    }
    cities = @(
        @{
            name = "Montreal"
            latitude = 45.5016
            longitude = -73.5672
            arrival_hour = 6
            distance_from_fire_miles = 357.4
            path_probability = 0.76
            Predicted_PM25_6h = 42.8
        }
    )
    forecast_hours = 6
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
    -Uri http://127.0.0.1:8000/api/v1/smoke/impact `
    -Method Post `
    -ContentType "application/json" `
    -Body $body
```

## Integration responsibilities

The prediction branch should provide:

- `name`, `latitude`, and `longitude`
- `arrival_hour`
- `predicted_pm25_6h`
- `path_probability` when available
- A distance in kilometres or miles

The integration layer should preserve the upstream PM2.5 value and should not
call this service once per feature or alter the city ordering. One request can
contain all predicted cities for the six-hour window.

The frontend or orchestration layer should combine:

1. The prediction branch's trajectory/map output.
2. This branch's `/smoke/impact` response.

That design keeps ownership clear and prevents duplicated calculations.
