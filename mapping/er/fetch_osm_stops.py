"""Download the bus stops and ferry terminals OpenStreetMap knows in the
Halifax area: the second source this lab matches against the GTFS feed.

    python mapping/er/fetch_osm_stops.py

Run from the repository root. You never need to run it:
er/osm-stops.csv is committed, a snapshot of OpenStreetMap as of
2026-10-19T20:01:51Z. Run it only to see how the file was made, or to take
a newer snapshot (the numbers in match-stops-result.txt will then change).

Source: the Overpass API (overpass-api.de), every node tagged
highway=bus_stop or amenity=ferry_terminal inside 44.55,-63.90 to
44.90,-63.25. Licence: OpenStreetMap data is (c) OpenStreetMap
contributors, under the Open Database License (ODbL) 1.0. osm-stops.csv is
an extract of it, so it is under the ODbL too, and anything built from it
must say so.

Unlike the course's own matching exercise, this is a real second source,
kept by different people for a different purpose. Its stops carry a "ref"
tag that is, most of the time, the GTFS stop code. The matcher never looks
at it; match_stops.py uses it only at the end, as the answer key.
"""

import csv
import json
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
URL = "https://overpass-api.de/api/interpreter"
QUERY = """[out:json][timeout:120];
(node["highway"="bus_stop"](44.55,-63.90,44.90,-63.25);
 node["amenity"="ferry_terminal"](44.55,-63.90,44.90,-63.25););
out body;"""


def main():
    # Overpass refuses a request with no User-Agent (406 Not Acceptable).
    req = Request(URL, data=urlencode({"data": QUERY}).encode(),
                  headers={"User-Agent": "UL-KR-course-lab/1.0 (education)"})
    try:
        data = json.load(urlopen(req, timeout=180))
    except OSError as e:
        sys.exit(f"Could not reach {URL}: {e}. The committed er/osm-stops.csv is enough for the lab.")
    rows = sorted(((e["id"], e["tags"].get("ref", ""), e["tags"].get("name", ""), e["lat"], e["lon"])
                   for e in data["elements"]), key=lambda r: r[0])
    with open(HERE / "osm-stops.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["osm_id", "ref", "name", "lat", "lon"])
        w.writerows(rows)
    stamp = data.get("osm3s", {}).get("timestamp_osm_base", "?")
    print(f"er/osm-stops.csv: {len(rows):,} OpenStreetMap stops, data as of {stamp}")
    print("(c) OpenStreetMap contributors, ODbL 1.0")


if __name__ == "__main__":
    main()
