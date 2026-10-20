# Triage of the SHACL results

Every rule of the Session 1 constraint inventory became a shape, and every
shape started as a Violation (`shapes-v0.ttl`). Run on the whole graph, the
first draft gave **23,208 Violations**. Each result was then judged with its
evidence: is it the **data's** fault, the **rule's** fault, or the
**conversion's** fault? `shapes.ttl` keeps the same rules and marks each
change with a `TRIAGE` comment.

## The results, one by one

| Result on the full graph | First draft | Whose fault | Evidence | Decision | Now |
|---|---:|---|---|---|---:|
| Times past midnight written in days (`P1DT1H10M`) | 13,694 | **the conversion's** | Session 2's converter wrote `PT25H10M`; rdflib rewrote it on write and on read. Same duration, wrong text for Linked GTFS. | Warning, fixed at the source: the mapping builds the text in SQL | 0 |
| A trip's shape is not a `gtfs:Shape` | 9,239 | **the rule's** | `shapes.txt` is not converted (1.3 million triples no question uses), so a shape IRI points at a node the graph does not describe | the rule now asks for one IRI | 0 |
| A stop shares its name with another stop | 268 | **the rule's** | Session 1, check 6: 133 names shared by 267 stops, 12 to 394 m apart, each with its own id. A name does not identify a stop. | Info, not deleted: the list entity resolution must not merge by name | 268 Info |
| Two headsigns in one direction | 5 | **the data's**, partly | 157 of 162 route-directions have one headsign; 4 exceptions are short or diverted trips (10C, 62, 9B), one is a spelling: route 72's `Portland Hills` and `PORTLAND HILLS` | Warning: worth a look by the publisher, not a reason to stop the feed | 5 Warnings |
| A service with no weekly rule | 2 | **the rule's** | GTFS allows a service defined only in `calendar_dates.txt` (259.1141.3, 259.1143.3; 66 rows, 10 trips) | the rule now accepts either kind of rule | 0 |

**After triage, on the deployed graph:** 0 Violations, 5 Warnings, 268 Info
(`runs/after-triage-mapped-graph.txt`). On Session 2's graph, before the
mapping fixed the times, the same shapes gave 0 Violations, 13,699
Warnings, 268 Info (`runs/after-triage-session2-graph.txt`).

**No invented error.** The Halifax feed has no error serious enough to stop
it. We did not plant one to make the gate look busy; the red run below uses
a deliberately broken copy, and says so.

## Two rules found false in the data, reported, not dropped

- **"One stop name, one stop"** is false: kept as Info.
- **"One headsign per route and direction"** is a pattern with exceptions:
  kept as a Warning, with the one real spelling fault named.

## SHACL or OWL, rule by rule

| Rule (Session 1 check) | Where | Why |
|---|---|---|
| A night trip is a trip | OWL (`tr:NightTrip rdfs:subClassOf gtfs:Trip`) | Meaning, used by inference: a query or shape on `gtfs:Trip` reaches night trips through it |
| Every stop time points to a trip and a stop that exist (1) | SHACL (`sh:class`, `sh:minCount`) | Closed world: "it must be there" is a check, and OWL would only infer the missing thing exists |
| Stops numbered 1, 2, 3 in a trip (2) | SHACL (SPARQL constraint) | Compares rows; no OWL axiom can |
| Times never go backwards in a trip (2) | SHACL (SPARQL, `trip-order-shape.ttl`) | Same; about 14 minutes on the whole graph, so CI runs it on the sample and Session 1's pandas check covers the feed |
| One headsign per direction (3) | SHACL, Warning | A pattern with exceptions; OWL has no severity |
| A vehicle never calls at a station (4) | **Both** | SHACL reports a Violation; in OWL, `gtfs:stop` has range `gtfs:Stop` and no stop is a station, so HermiT finds the broken sample inconsistent |
| Times as `PT..H..M`, past 24:00 allowed (5) | SHACL (`sh:pattern`) | About how the data is written; OWL says nothing about text |
| No route is a fare rule, no stop is a station | OWL (disjointness) | Lets the reasoner find contradictions; it found the Linked GTFS range error |
| A stop served by exactly one route (CQ 4) | SPARQL / SHACL | Under the open world, OWL can never conclude "exactly one" |

## The red run

The gate is meant to stop bad data. `runs/red-run-pipeline-sample.txt`:
the pipeline on the CI sample with one value changed, trip 4648930's second
stop time calling at Bridge Terminal (the station 10001) instead of stop
7605 inside it:

```text
Violation      1  Every stop time | Class on stop   e.g. stoptime/4648930/2
GATE: FAIL, 1 violations. Exit code 1.
SHACL gate: the data has Violations, so the endpoint is not loaded.
```

To see it in CI: on a branch, change that row of `data/example.sql`
(`stop_id` 7605 to 10001 for trip 4648930, stop_sequence 2) and push; keep
the red run's link for the report.
