# mapping/

From the operational tables to the graph (Session 5).

| File | What it is |
|---|---|
| `mapping.ttl` | The R2RML mapping: 22 triples maps, the eight GTFS tables to Linked GTFS. The pipeline runs it with Morph-KGC on every start. |
| `materialize-and-compare.txt` | Session 5's check: the mapped graph against Session 2's converter, triple by triple |
| `virtualized/` | The same mapping run virtualized, by Ontop over PostgreSQL: one question, its answers and the SQL Ontop wrote |
| `er/` | Entity resolution: our stops against OpenStreetMap's, with precision and recall |

## Two choices in the mapping

- **Times are built as text in SQL.** `" 5:49:00"` becomes `PT5H49M` and
  `25:10:00` becomes `PT25H10M`, as Linked GTFS asks, and rdflib's rewriting
  is turned off when the graph is written. This removed the 13,694 time
  Warnings of Session 4.
- **A missing value is left out by `WHERE`, not by `NULL`.** Morph-KGC 2.10
  writes a NULL as the text "None" (about 648,000 `gtfs:None` on the first
  try), so each optional column has its own small triples map.

## Materialized or virtualized: the deployed system materializes

| | Materialized (deployed) | Virtualized (Ontop) |
|---|---|---|
| Freshness | Rebuilt per feed snapshot; the feed changes every few months | Always current, which a timetable does not need |
| Latency | Under a second per question | About 3 s for one question |
| Workload | The SHACL gate checks the whole graph before anyone queries it | Answers from data no gate has seen |

Ontop also showed the night trip trap a third way: with the vocabulary it
reasons that a night trip is a trip and counts each of the 217 twice (9,044
bus trips); with `--no-tbox`, 8,827 (`virtualized/ontop-run.txt`). It was
run in the course repository's Session 5 lab, against PostgreSQL; this
stack does not run a PostgreSQL.

## Entity resolution (`er/`)

Our 2,347 GTFS stops against OpenStreetMap's 2,536 Halifax stops (ODbL,
snapshot 2026-10-19, committed). OpenStreetMap's `ref` tag is usually the
GTFS stop code, so it is a real answer key; the matcher uses only the names
(codes removed) and the distance, Fellegi-Sunter weights, blocking at 200 m.

| Threshold | Precision | Recall |
|---|---|---|
| 6 | 0.972 | 0.959 |
| 14 | 0.999 | 0.808 |

```sh
python mapping/er/match_stops.py      # from the repository root, after data/fetch_data.py
```

The errors that remain are Session 1's lesson again: two stops with the
same name across the road from each other.
