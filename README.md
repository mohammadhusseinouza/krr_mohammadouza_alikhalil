# A checked knowledge graph of Halifax Transit

The Knowledge Representation team project (Lebanese University, MSc), built
on the course's `kr-team-template`. It turns Halifax Transit's published
timetable (a GTFS feed) into a knowledge graph that is **checked** (SHACL,
OWL), **traceable** (every file and its SHA-256), and **answerable in
English** by someone who knows no SPARQL, with a refusal when the graph
cannot answer.

The labs and slides of the course are at
https://ahmabboud.github.io/course_knowledge_representation/.

## Run it

```sh
cp .env.example .env        # then put ONE key in .env: ANTHROPIC_API_KEY (Claude) or GOOGLE_API_KEY (Gemini)
docker compose up --build
```

On Windows, use PowerShell: `Copy-Item .env.example .env`, then the same
`docker compose up --build`.

**Expect**, the first time, about 15 minutes (most of it the SHACL gate on
two million triples):

```text
1 source: the Halifax feed, SHA-256 checked; 8 tables, 324,165 stop times -> build/halifax.sqlite
2 map: 2,034,562 triples -> build/graph.nt
3 validate: validated in 650 s ... 0 Violation, 5 Warning, 268 Info -> build/shacl-gate.txt
4 describe: 486 VoID triples -> build/void.ttl
5 provenance: 8 source files and 4 more inputs, with their SHA-256 -> build/provenance.ttl
6 load: 2,035,616 triples in the default graph, provenance in a named graph -> http://fuseki:3030/kr
done
```

Then the access layer serves on http://127.0.0.1:8000. Try
`http://127.0.0.1:8000/?question=How%20many%20trips%20run%20on%20route%201%3F&dataset=https://ul.edu.lb/kr/halifax/`
(the answer is 496), or a question the graph cannot answer, such as
`Which%20stops%20are%20wheelchair%20accessible%3F` (refused: the feed has
no information on it). The endpoint is at http://127.0.0.1:3030 (dataset
`kr`). A restart with the same inputs skips the gate, and is up in about
3 minutes.

**The data** is downloaded on the first run and checked against its
SHA-256: a dated snapshot of the feed from the Mobility Database
(`mdb-734-202608240120`), so every run sees the same data.

## What is where

| Folder | Layer | Session | What it holds |
|---|---|---|---|
| `data/` | the source | 1, 5 | `fetch_data.py` (the feed, checksummed), `example.sql` (7 real trips, for CI) |
| `ontology/` | the ontology | 3 | Linked GTFS reused (a corrected copy), our extension, release 1.1.0, competency questions, the reasoner run |
| `shapes/` | SHACL | 4 | the gate's shapes, the first draft, the triage, the red run |
| `mapping/` | R2RML and integration | 5 | the mapping, the virtualized run (Ontop), entity resolution against OpenStreetMap |
| `pipeline/` | source, map, gate, describe, load | 4, 5 | `run.py`: any Violation stops it before the endpoint |
| `model/` | learning over the graph | 6 | night trip classification and route-serves-stop link prediction, with baselines and splits |
| `access-layer/` | questions in English | 7 | Claude or Gemini, grounded in the VoID, checked, repaired, or refused; the test set |
| `report/` | the technical report | all | `REPORT.md` |
| `.github/workflows/` | the gate in CI | 4 | maps and validates `data/example.sql` on every push |

## How the stack fits together

```text
feed (dated, SHA-256) --> SQLite --> map (mapping/) --> SHACL gate (shapes/ + ontology/)
                                                            |
                                        Violation: stop     |  pass
                                                            v
                         VoID (build/void.ttl) + provenance + load --> Fuseki (kr)
                                                                          ^
               a question in English --> access layer (Claude or Gemini) -+
```

The endpoint is only ever loaded with data that passes the gate. To see it
stop: change one row of `data/example.sql` so a bus calls at a station
(`shapes/triage.md`, "The red run") and run
`python pipeline/run.py --sample --no-load`.

## The Session 7 checklist

| Check | Where |
|---|---|
| One command from a clean checkout | `docker compose up --build`; the feed is fetched and checksummed |
| Services on 127.0.0.1 only, keys only in `.env` | `docker-compose.yml`; `.env` is gitignored |
| The SHACL gate before the endpoint and in CI | `pipeline/run.py` step 3; `.github/workflows/shacl-gate.yml` |
| The test set's score, with model and date | `report/access-layer-score.txt` |
| A real unanswerable question refused, with a reason | wheelchair access, ridership, real-time delays (`access-layer/questions.yaml`) |

## Without Docker

Python 3.12, from the repository root:

```sh
pip install -r pipeline/requirements-pipeline.txt
pip install --no-deps morph-kgc==2.10.0
python pipeline/run.py --no-load
```

## Licences

| Ontology, vocabulary or dataset | Licence | Where used |
|---|---|---|
| Halifax Transit GTFS feed | Open Government Licence – Halifax (attribution) | the data |
| Linked GTFS (Colpaert and Byrd, Open Transport) | CC BY 3.0 | `ontology/`: reused, and a corrected copy that lists its changes |
| OpenStreetMap stops | ODbL 1.0, © OpenStreetMap contributors | `mapping/er/` |
