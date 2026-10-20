"""Match OpenStreetMap's stops to the GTFS feed's stops, and measure the error.

    python mapping/er/match_stops.py                 # both thresholds
    python mapping/er/match_stops.py --threshold 10

Run from the repository root, after data/fetch_data.py (the database is
not needed). The recorded run is match-stops-result.txt. Reads er/osm-stops.csv and the feed's stops.txt,
and only at the end the "ref" tags in osm-stops.csv, to count the mistakes.

The method, Fellegi and Sunter's (1969), in four steps:
1. Clean both names the same way: the stop code taken out ("7016 - Kearney
   Lake Rd ..." and "Kearney Lake Rd ... (7016)" both become "KEARNEY LAKE
   RD ..."), upper case, single spaces. The code is removed on purpose: it is
   the answer, and a matcher that read it would not be matching.
2. Blocking: compare only stops less than 200 m apart, not every pair.
3. For each pair, compare two fields, the distance and the name. Each
   outcome adds a weight log2(m / u), where m is how often the outcome
   happens for the same stop and u how often for two different stops. The
   weights below are stated, not learned; Splink estimates them from the
   data, for the same model at scale.
4. Pair each OpenStreetMap stop with its best GTFS candidate. Above the
   threshold, call it a match.

The answer key: an OpenStreetMap stop whose ref is a stop code of the feed
is that stop; any other OpenStreetMap stop has no match in the feed. The
key is itself data, typed by OpenStreetMap volunteers, so a "wrong match"
can now and then be a wrong ref. Read the examples before trusting a number.
"""

import argparse
import csv
import math
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
STOPS_TXT = HERE.parents[1] / "data" / "halifax" / "gtfs" / "stops.txt"

# outcome: (m, u) = P(outcome | same stop), P(outcome | different stops)
WEIGHTS = {
    "under 15 m": (0.80, 0.0005), "15 to 50 m": (0.18, 0.004), "50 to 200 m": (0.02, 0.9955),
    "name same": (0.85, 0.01), "name close": (0.10, 0.05), "name different": (0.05, 0.94),
}
THRESHOLDS = (6, 14)
BLOCK_M = 200


def clean_name(name):
    name = re.sub(r"\s*\(\d+\)\s*$", "", name)   # GTFS: "... (7016)"
    name = re.sub(r"^\d+\s*(-\s*)?", "", name)    # OpenStreetMap: "7016 - ..." or "7016 ..."
    return re.sub(r"\s+", " ", name).strip().upper()


def metres(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def jaro_winkler(a, b):
    if a == b:
        return 1.0
    reach = max(len(a), len(b)) // 2 - 1
    ma, mb = [False] * len(a), [False] * len(b)
    m = 0
    for i, ca in enumerate(a):
        for j in range(max(0, i - reach), min(len(b), i + reach + 1)):
            if not mb[j] and b[j] == ca:
                ma[i] = mb[j] = True
                m += 1
                break
    if not m:
        return 0.0
    sa = [c for c, f in zip(a, ma) if f]
    sb = [c for c, f in zip(b, mb) if f]
    t = sum(x != y for x, y in zip(sa, sb)) / 2
    jaro = (m / len(a) + m / len(b) + (m - t) / m) / 3
    prefix = next((k for k in range(min(4, len(a), len(b))) if a[k] != b[k]), min(4, len(a), len(b)))
    return jaro + prefix * 0.1 * (1 - jaro)


def score(o, g, d):
    outcomes = ["under 15 m" if d <= 15 else "15 to 50 m" if d <= 50 else "50 to 200 m"]
    if o["name"]:  # 120 OpenStreetMap stops are named only by their code: no name left to compare
        outcomes.append("name same" if o["name"] == g["name"] else
                        "name close" if jaro_winkler(o["name"], g["name"]) >= 0.9 else "name different")
    return sum(math.log2(WEIGHTS[x][0] / WEIGHTS[x][1]) for x in outcomes), outcomes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--threshold", type=float, action="append")
    ap.add_argument("--examples", type=int, default=5, help="wrong matches and misses shown per threshold")
    args = ap.parse_args()
    thresholds = args.threshold or THRESHOLDS

    s = pd.read_csv(STOPS_TXT, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    s = s[s["location_type"] != "1"]  # stations are not stops a vehicle calls at
    gtfs = [{"code": c, "name": clean_name(n), "raw": n, "lat": float(la), "lon": float(lo)}
            for c, n, la, lo in zip(s["stop_code"], s["stop_name"], s["stop_lat"], s["stop_lon"])]
    osm = [{"id": r["osm_id"], "ref": r["ref"], "raw": r["name"], "name": clean_name(r["name"]),
            "lat": float(r["lat"]), "lon": float(r["lon"])}
           for r in csv.DictReader(open(HERE / "osm-stops.csv", encoding="utf-8"))]

    # Blocking: a cheap box first (0.002 degrees is over 200 m here), then the real distance.
    pairs = 0
    best = {}
    for o in osm:
        for g in gtfs:
            if abs(o["lat"] - g["lat"]) > 0.002 or abs(o["lon"] - g["lon"]) > 0.003:
                continue
            d = metres(o["lat"], o["lon"], g["lat"], g["lon"])
            if d > BLOCK_M:
                continue
            pairs += 1
            sc, why = score(o, g, d)
            if o["id"] not in best or sc > best[o["id"]][0]:
                best[o["id"]] = (sc, g, why, d)
    print(f"{len(osm):,} OpenStreetMap stops, {len(gtfs):,} GTFS stops: {len(osm) * len(gtfs):,} possible pairs, "
          f"{pairs:,} after blocking on {BLOCK_M} m")
    print(f"{sum(1 for o in osm if o['id'] not in best)} OpenStreetMap stops have no GTFS stop within {BLOCK_M} m")

    codes = {g["code"] for g in gtfs}
    truth = {o["id"]: (o["ref"] if o["ref"] in codes else None) for o in osm}
    raw = {o["id"]: o for o in osm}
    n_true = sum(1 for v in truth.values() if v)
    print(f"answer key: {n_true:,} OpenStreetMap stops carry a feed stop code; "
          f"{len(osm) - n_true} do not (a stop not in this feed, or no ref)")
    for th in thresholds:
        found = {oid: b[1]["code"] for oid, b in best.items() if b[0] >= th}
        tp = sum(1 for oid, code in found.items() if truth[oid] == code)
        fp = [oid for oid, code in found.items() if truth[oid] != code]
        fn = [oid for oid, code in truth.items() if code and found.get(oid) != code]
        p, r = tp / max(len(found), 1), tp / n_true
        print(f"\nthreshold {th:g}: {len(found):,} matches, {tp:,} right. precision {p:.3f}, recall {r:.3f}")
        print(f"  {len(fp)} wrong matches, {len(fn)} misses; the first {args.examples} of each:")
        for oid in sorted(fp, key=lambda k: -best[k][0])[: args.examples]:
            sc, g, why, d = best[oid]
            print(f"  wrong match  {raw[oid]['raw']!r:<48} -> {g['raw']!r}, {d:.0f} m, score {sc:.1f} "
                  f"(truth: {truth[oid] or 'not in the feed, ref ' + (raw[oid]['ref'] or 'none')})")
        for oid in fn[: args.examples]:
            b = best.get(oid)
            what = f"best score {b[0]:.1f}: {', '.join(b[2])}" if b else f"nothing within {BLOCK_M} m"
            print(f"  missed       {raw[oid]['raw']!r:<48}    (truth: {truth[oid]}; {what})")


if __name__ == "__main__":
    main()
