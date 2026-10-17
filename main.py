import csv
import io
import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()
MAP_KEY = "1f518a4942653d6b8a5976c10a2debdf"

if not MAP_KEY:
    print("MAP_KEY not found. Create a .env file with: MAP_KEY=your_key_here")
    raise SystemExit

# ---------- 1. Fire locations (NASA FIRMS) -> fires.json ----------
# Area = west, south, east, north (a box around the UK). Last number = days (1-5).
url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/-8.7,49.8,1.9,60.9/1"

response = requests.get(url)

# If the key is wrong, NASA sends an error message instead of CSV data
if "latitude" not in response.text:
    print("Error from NASA:", response.text)
    raise SystemExit

fires = []
for row in csv.DictReader(io.StringIO(response.text)):
    fires.append({
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
        "date": row["acq_date"],
        "time": row["acq_time"],
        "confidence": row["confidence"],
    })

with open("fires.json", "w") as file:
    json.dump(fires, file, indent=2)

print(f"Saved {len(fires)} fire locations to fires.json")

# ---------- 2. Wind in each city (Open-Meteo, no API key needed) -> wind.json ----------
cities = {
    "London": (51.5074, -0.1278),
    "Birmingham": (52.4862, -1.8904),
    "Manchester": (53.4808, -2.2426),
    "Leeds": (53.8008, -1.5491),
    "Glasgow": (55.8642, -4.2518),
    "Liverpool": (53.4084, -2.9916),
    "Newcastle": (54.9783, -1.6178),
    "Sheffield": (53.3811, -1.4701),
    "Bristol": (51.4545, -2.5879),
    "Edinburgh": (55.9533, -3.1883),
    "Cardiff": (51.4816, -3.1791),
    "Belfast": (54.5973, -5.9301),
    "Nottingham": (52.9548, -1.1581),
    "Southampton": (50.9097, -1.4044),
    "Aberdeen": (57.1497, -2.0943),
    "Inverness": (57.4778, -4.2247),
    "Plymouth": (50.3755, -4.1427),
    "Norwich": (52.6309, 1.2974),
    "Cambridge": (52.2053, 0.1218),
    "Exeter": (50.7184, -3.5339),
}

names = list(cities.keys())
lats = ",".join(str(cities[n][0]) for n in names)
lons = ",".join(str(cities[n][1]) for n in names)

wind_url = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={lats}&longitude={lons}"
    "&current=wind_speed_10m,wind_direction_10m"
)
wind_data = requests.get(wind_url).json()

if isinstance(wind_data, dict):  # an error message comes back as a dict
    print("Error from Open-Meteo:", wind_data.get("reason"))
    raise SystemExit

city_wind = []
for name, weather in zip(names, wind_data):
    city_wind.append({
        "city": name,
        "latitude": cities[name][0],
        "longitude": cities[name][1],
        "wind_speed_kmh": weather["current"]["wind_speed_10m"],
        "wind_direction_deg": weather["current"]["wind_direction_10m"],
    })

with open("wind.json", "w") as file:
    json.dump(city_wind, file, indent=2)

print(f"Saved wind for {len(city_wind)} cities to wind.json")