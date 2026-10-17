import csv
import io
import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()
MAP_KEY = os.getenv("MAP_KEY")

if not MAP_KEY:
    print("MAP_KEY not found. Create a .env file with: MAP_KEY=your_key_here")
    raise SystemExit

# ---------- 1. Fire locations (NASA FIRMS) -> fires.json ----------
# Area = west, south, east, north (a box around Indonesia). Last number = days (1-5).
url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/95,-11,141,6/1"

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
    "Jakarta": (-6.2088, 106.8456),
    "Surabaya": (-7.2575, 112.7521),
    "Bandung": (-6.9175, 107.6191),
    "Medan": (3.5952, 98.6722),
    "Semarang": (-6.9667, 110.4167),
    "Makassar": (-5.1477, 119.4327),
    "Palembang": (-2.9761, 104.7754),
    "Denpasar": (-8.6705, 115.2126),
    "Balikpapan": (-1.2379, 116.8529),
    "Pontianak": (-0.0263, 109.3425),
    "Banjarmasin": (-3.3194, 114.5908),
    "Pekanbaru": (0.5071, 101.4478),
    "Jambi": (-1.6101, 103.6131),
    "Palangkaraya": (-2.2161, 113.9135),
    "Manado": (1.4748, 124.8421),
    "Jayapura": (-2.5337, 140.7181),
    "Padang": (-0.9471, 100.4172),
    "Yogyakarta": (-7.7956, 110.3695),
    "Ambon": (-3.6954, 128.1814),
    "Kupang": (-10.1772, 123.6070),
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
