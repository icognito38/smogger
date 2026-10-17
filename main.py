import csv
import io
import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()  # reads the .env file in the same folder
MAP_KEY = os.getenv("MAP_KEY")

if not MAP_KEY:
    print("MAP_KEY not found. Create a .env file with: MAP_KEY=your_key_here")
    raise SystemExit

# Area = west, south, east, north (a box around Indonesia). Last number = days (1-5).
url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/95,-11,141,6/1"

response = requests.get(url)

# If the key is wrong, NASA sends an error message instead of CSV data
if "latitude" not in response.text:
    print("Error from NASA:", response.text)
    raise SystemExit

rows = csv.DictReader(io.StringIO(response.text))

fires = []
for row in rows:
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