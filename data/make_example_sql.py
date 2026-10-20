"""Write data/example.sql: a small, real slice of the Halifax feed, for CI.

    python data/make_example_sql.py

Run from the repository root, after data/fetch_data.py. The SHACL gate in CI
(.github/workflows/shacl-gate.yml) maps and validates this slice on every
push, so the gate runs without downloading the 29 MB feed; the stack itself
always runs on the whole feed.

The slice is Session 4's CI sample: seven real trips, each chosen so a shape
has something real to look at, with everything the mapping and the shapes
need to check them: their stop times, the stops they call at and those
stops' stations, their routes, the agency, the feed, and their services'
weekly and date rules. Every value is copied as text, exactly as the feed
writes it (a time keeps its stray space), as the stack's database does.
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GTFS = ROOT / "data" / "halifax" / "gtfs"
OUT = ROOT / "data" / "example.sql"

TRIPS = [
    "4648930",   # route 1, the first row of trips.txt; ends at stop 7605, inside Bridge Terminal
    "4824030",   # route FerD, the Alderney ferry
    "4824029",   # route FerD again
    "4649002",   # route 1, a night trip: it runs past 24:00:00
    "4658187",   # route 72, direction 1, headsign "PORTLAND HILLS"
    "4658188",   # route 72, direction 1, headsign "Portland Hills" (Session 1, check 3)
    "4650140",   # route 123, service 259.1141.3: only in calendar_dates.txt, no weekly rule
]
TABLES = ["agency", "feed_info", "routes", "trips", "stops", "stop_times", "calendar", "calendar_dates"]


def table(name):
    return pd.read_csv(GTFS / f"{name}.txt", dtype=str, keep_default_na=False, encoding="utf-8-sig")


def sql(name, df):
    cols = list(df.columns)
    out = [f"DROP TABLE IF EXISTS {name};",
           f"CREATE TABLE {name} ({', '.join(f'{c} TEXT' for c in cols)});"]
    for row in df.itertuples(index=False):
        values = ", ".join("'" + str(v).replace("'", "''") + "'" for v in row)
        out.append(f"INSERT INTO {name} VALUES ({values});")
    return "\n".join(out)


def main():
    t = {name: table(name) for name in TABLES}
    trips = t["trips"][t["trips"].trip_id.isin(TRIPS)]
    stop_times = t["stop_times"][t["stop_times"].trip_id.isin(TRIPS)]
    called = set(stop_times.stop_id)
    stations = set(t["stops"][t["stops"].stop_id.isin(called)].parent_station) - {""}
    keep = {
        "agency": t["agency"],
        "feed_info": t["feed_info"],
        "routes": t["routes"][t["routes"].route_id.isin(set(trips.route_id))],
        "trips": trips,
        "stops": t["stops"][t["stops"].stop_id.isin(called | stations)],
        "stop_times": stop_times,
        "calendar": t["calendar"][t["calendar"].service_id.isin(set(trips.service_id))],
        "calendar_dates": t["calendar_dates"][t["calendar_dates"].service_id.isin(set(trips.service_id))],
    }
    head = ("-- A real slice of the Halifax Transit GTFS feed (snapshot mdb-734-202608240120,\n"
            "-- Open Government Licence - Halifax), for the SHACL gate in CI.\n"
            "-- Written by data/make_example_sql.py: regenerate, do not edit.\n"
            f"-- Trips: {', '.join(TRIPS)}.\n")
    OUT.write_text(head + "\n\n".join(sql(n, keep[n]) for n in TABLES) + "\n", encoding="utf-8")
    for n in TABLES:
        print(f"{n:<15} {len(keep[n]):>5} rows")
    print(f"-> {OUT.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
