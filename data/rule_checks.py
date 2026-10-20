"""Session 1 lab: six rule checks on the Halifax Transit GTFS feed, each printed with its count.

Run from the repository root after `python data/fetch_data.py`:

    python data/rule_checks.py

Nothing to edit. Read each block: the question, the count, and what it means.
Then copy the numbers into constraint_inventory.csv.
"""
from pathlib import Path

import pandas as pd

GTFS_DIR = Path(__file__).resolve().parent / "halifax" / "gtfs"
GTFS_TABLES = {p.stem: p for p in GTFS_DIR.glob("*.txt")}

# Read as text: GTFS ids such as "10A" or "259.0.1" are names, not numbers.
read = lambda name: pd.read_csv(GTFS_TABLES[name], dtype=str, keep_default_na=False)  # noqa: E731
stop_times, trips, stops = read("stop_times"), read("trips"), read("stops")


def show(n, question, result, meaning):
    print(f"\nCheck {n}: {question}\n  Result : {result}\n  Meaning: {meaning}")


def seconds(t):
    h, m, s = t.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


# 1. Every stop time points to a real trip and a real stop
bad = (~stop_times["trip_id"].isin(trips["trip_id"]) | ~stop_times["stop_id"].isin(stops["stop_id"])).sum()
show(1, "Does every row of stop_times point to a trip in trips.txt and a stop in stops.txt?",
     f"{bad} of {len(stop_times)} stop times break it",
     "No exceptions: a rule across three tables that the data always obeys, and no file states it.")

# 2. Inside a trip, order and time agree
s = stop_times.assign(sec=stop_times["arrival_time"].map(seconds),
                      seq=stop_times["stop_sequence"].astype(int)).sort_values(["trip_id", "seq"])
by_trip = s.groupby("trip_id")
backwards = int((by_trip["sec"].diff() < 0).sum())
gaps = int((by_trip["seq"].diff().dropna() != 1).sum()) + int((by_trip["seq"].min() != 1).sum())
show(2, "Inside each trip, do stop_sequence values run 1, 2, 3... and do times never go backwards?",
     f"{backwards} backward steps and {gaps} sequence gaps across {s['trip_id'].nunique()} trips",
     "Again no exceptions: a rule between rows of one table, which a column type can never express.")

# 3. Route, direction and headsign
heads = trips.groupby(["route_id", "direction_id"])["trip_headsign"].agg(lambda x: x.value_counts().to_dict())
print("\nCheck 3: Does each route, in each direction, show one headsign (the destination on the sign)?")
print(f"  {len(heads)} route-directions: {(heads.map(len) == 1).sum()} have one headsign. The others:")
for (route, direction), signs in heads[heads.map(len) > 1].items():
    print(f"    route {route}, direction {direction}: {signs}")
print("  Meaning: almost always one, except a few short or diverted trips, and route 72 where the same")
print("  sign is spelled in two cases. The pattern is real; its exceptions are where the questions are.")

# 4. Stations and the stops inside them
kind = dict(zip(stops["stop_id"], stops["location_type"]))
at_station = int(stop_times["stop_id"].map(kind).eq("1").sum())
parents = stops.loc[stops["parent_station"] != "", "parent_station"].map(kind)
show(4, "Do trips stop only at stops, never at a station itself, and is every parent_station a station?",
     f"{at_station} stop times at one of the {sum(v == '1' for v in kind.values())} stations; "
     f"{int((parents == '1').sum())} of {len(parents)} parent_station values point to a station",
     "A station is a place that holds stops; vehicles stop at the stops inside it. Two kinds of thing in one table.")

# 5. Time values
t = stop_times["arrival_time"]
hours = t.str.strip().str.split(":").str[0].astype(int)
show(5, "Are arrival times all in HH:MM:SS, and all below 24:00:00?",
     f"{int(t.str.startswith(' ').sum())} of {len(t)} start with a space and one hour digit (e.g. {t.iloc[0]!r}); "
     f"{int((hours >= 24).sum())} are 24:00:00 or later (latest {t.str.strip()[hours.idxmax()]}), "
     f"on {stop_times.loc[hours >= 24, 'trip_id'].nunique()} trips",
     "Opposite verdicts. The space breaks the GTFS format (HH:MM:SS); the hours past 24 are correct GTFS: "
     "a trip after midnight still belongs to the service day it started on.")

# 6. Same stop name, different stops
base = stops["stop_name"].str.replace(r"\s*\(\d+\)$", "", regex=True)
counts = base.value_counts()
shared = counts[counts > 1]
example = stops.loc[base == "Barrington St Before North St", ["stop_id", "stop_lat", "stop_lon"]]
show(6, "Once the '(stop code)' is removed from stop_name, is each name one stop?",
     f"{len(shared)} names are shared by {int(shared.sum())} stops, for example 'Barrington St Before North St':\n"
     + example.to_string(index=False).replace("\n", "\n    ").join(["    ", ""]),
     "Different stops with their own id and position, 12 to 394 m apart (median 89 m, "
     "session1_facts.py). The name alone does not identify a stop; merging them would be wrong.")
