# data/

**The source:** Halifax Transit's GTFS Schedule feed (Halifax Regional
Municipality, Nova Scotia), Open Government Licence – Halifax. Fetched, not
committed.

- `fetch_data.py` downloads the dated snapshot `mdb-734-202608240120` from
  the Mobility Database archive (captured 2026-08-24, `feed_version`
  `2026_08_August_20260806`, valid 2026-08-24 to 2026-11-29), checks its
  SHA-256, and extracts the nine tables to `halifax/gtfs/`. The agency's own
  URL always serves its newest feed, so it can have no fixed checksum; the
  snapshot never changes. It also fetches Linked GTFS as published, pinned to
  commit `fc12d51`, to `linked-gtfs/gtfs.ttl`. The pipeline runs it first.
- `example.sql` is a real slice of the feed for CI: 7 trips, chosen so each
  shape has something real to look at, with everything they need (163 stop
  times, 128 stops, 4 routes, their services and date rules).
  `make_example_sql.py` writes it; regenerate, do not edit.

| Table | Rows | One row is |
|---|---:|---|
| `agency.txt` | 1 | Halifax Transit |
| `routes.txt` | 81 | a route: 79 bus routes, 2 ferry routes |
| `trips.txt` | 9,239 | one run of a route on one service pattern |
| `stops.txt` | 2,358 | a stop or station: 11 stations, 60 stops inside them |
| `stop_times.txt` | 324,165 | one trip calling at one stop, at a time, as stop number N |
| `calendar.txt` | 7 | a weekly service pattern |
| `calendar_dates.txt` | 82 | an exception on one date (a service added or removed) |
| `shapes.txt` | 326,349 | a point of the line a vehicle draws (not mapped: no question uses it) |
| `feed_info.txt` | 1 | the feed: publisher, version, validity |

`stop_times.txt` has no single key: a row is its `trip_id` and its
`stop_sequence` together, and so is its IRI
(`https://ul.edu.lb/kr/id/stoptime/halifax/4648930/1`).

**Two findings that shaped everything after** (Session 1): 76,774 times
start with a space (`' 5:49:00'`, which breaks GTFS), and 6,847 are past
24:00 (`25:10:00`, which GTFS allows: the trip still belongs to the day it
started). The mapping writes both as `xsd:duration` (`PT5H49M`, `PT25H10M`).

## The constraint inventory (Session 1)

`constraint_inventory.csv` lists each rule the data obeys, with the count
behind it. `rule_checks.py` recomputes the six checks on the feed
(`runs/rule-checks.txt`); the shapes in `shapes/` come from them, and
`shapes/triage.md` says which held, which did not, and why.

```sh
python data/rule_checks.py        # from the root, after data/fetch_data.py; a few seconds
```

`runs/openrefine-clusters.txt` records the stop name clustering: 0 clusters
as published, 93 once the codes are removed, and every one of the 93 a
wrong merge ("A after B" and "B after A" are two stops on two streets).
