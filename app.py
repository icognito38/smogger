from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__)

# Regions with an AQI (Air Quality Index) above this are "high smog" -> red
HIGH_SMOG_AQI = 150

# Each region is a polygon: a list of [lat, lon] corner points.
# The map joins the points with straight lines (and closes the shape).
# This is sample data (South Kalimantan traced from the project picture).
# Replace it at any time by sending your own data to POST /data
regions = [
    {
        "name": "South Kalimantan",
        "aqi": 220,
        "polygon": [
            [-1.50, 116.23], [-1.69, 116.33], [-1.91, 116.21], [-2.15, 116.35],
            [-2.36, 116.62], [-2.48, 117.27], [-2.52, 117.95], [-3.28, 117.97],
            [-3.81, 117.44], [-5.19, 116.90], [-4.71, 115.17], [-4.97, 114.66],
            [-4.09, 114.93], [-3.30, 115.09], [-2.60, 115.41], [-2.07, 115.70],
            [-1.77, 115.95],
        ],
    },
    {
        "name": "Central Kalimantan",
        "aqi": 70,
        "polygon": [[-1.2, 111.6], [-1.2, 113.8], [-3.2, 113.8], [-3.2, 111.6]],
    },
]


@app.route("/")
def home():
    # Serve index.html from the same folder as app.py
    return send_from_directory(app.root_path, "index.html")


@app.route("/data", methods=["GET"])
def get_data():
    # Send every region to the page, marking the high-smog ones
    result = []
    for r in regions:
        result.append({**r, "high": r["aqi"] > HIGH_SMOG_AQI})
    return jsonify(result)


@app.route("/data", methods=["POST"])
def receive_data():
    # Receive a JSON list:
    # [{"name": ..., "aqi": ..., "polygon": [[lat, lon], [lat, lon], ...]}, ...]
    global regions
    new_data = request.get_json(silent=True)

    if not isinstance(new_data, list):
        return jsonify(error="Send a JSON list of regions"), 400

    try:
        cleaned = []
        for r in new_data:
            polygon = [[float(p[0]), float(p[1])] for p in r["polygon"]]
            if len(polygon) < 3:
                raise ValueError("a polygon needs at least 3 points")
            cleaned.append({
                "name": str(r["name"]),
                "aqi": float(r["aqi"]),
                "polygon": polygon,
            })
    except (KeyError, TypeError, ValueError, IndexError):
        return jsonify(error="Each region needs name, aqi and a polygon of at least 3 [lat, lon] points"), 400

    regions = cleaned
    return jsonify(status="ok", count=len(regions))


if __name__ == "__main__":
    app.run(debug=True)