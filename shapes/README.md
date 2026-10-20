# shapes/

The SHACL gate (Session 4). The pipeline validates the whole graph, with
the ontology, against `shapes.ttl` before anything is loaded: **any
Violation stops it**, and the endpoint keeps the last graph that passed.

| File | What it is |
|---|---|
| `shapes.ttl` | The gate's shapes, after triage: one per Session 1 rule, each naming its rule, each change marked `TRIAGE` |
| `trip-order-shape.ttl` | "Times never go backwards in a trip": right, but about 14 minutes on the whole graph, so it runs in CI on the sample |
| `shapes-v0.ttl` | The first draft, every rule a Violation, kept as the triage's evidence |
| `triage.md` | Every result, whose fault it was, the decision, and SHACL or OWL for each rule |
| `validate.py` | pySHACL with a readable report: focus nodes per shape, results grouped, exit code 1 on a Violation |
| `runs/` | The recorded runs: first draft, after triage (both graphs), the pipeline's red run |

**Results on the deployed graph:** 0 Violations, 5 Warnings (headsigns),
268 Info (shared stop names), in about 11 minutes.

Run it on its own (after `python pipeline/run.py --no-load` has written
`build/graph.nt`):

```sh
cd shapes
python validate.py --data ../build/graph.nt --data ../ontology/ontology.ttl --shapes shapes.ttl
```

`validate.py` sets `rdflib.NORMALIZE_LITERALS = False`: by default rdflib
rewrites `PT25H10M` into `P1DT1H10M` as it reads, so a rule about how a
time is written would test rdflib, not the data (found in Session 4).
