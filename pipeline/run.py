"""The graph pipeline: feed -> database -> graph -> SHACL gate -> VoID -> endpoint.

    python pipeline/run.py                     all steps on the whole feed, loads the endpoint
    python pipeline/run.py --no-load           steps 1 to 6 only (no Fuseki needed)
    python pipeline/run.py --sample --no-load  CI: data/example.sql, 7 trips, plus the time-order shape
    python pipeline/run.py --regate            validate again even if these inputs passed before

Run from the repository root. In the stack, docker compose runs it once, as
the "pipeline" service, before the access layer starts.

  1 source     the Halifax feed, fetched and SHA-256 checked (data/fetch_data.py),
               its eight tables into build/halifax.sqlite, every value as text;
               with --sample, data/example.sql instead
  2 map        mapping/mapping.ttl with Morph-KGC -> build/graph.nt
  3 validate   build/graph.nt + ontology/ontology.ttl against shapes/shapes.ttl;
               any Violation stops here (exit 1), so bad data never reaches
               the endpoint; the report goes to build/shacl-gate.txt
  4 describe   VoID of what the endpoint will hold -> build/void.ttl (the access layer reads it)
  5 provenance which files, with which SHA-256, made this graph -> build/provenance.ttl
  6 load       graph, ontology and Linked GTFS into the endpoint's default graph;
               the provenance in a named graph (FUSEKI_URL, dataset kr)

The gate takes about 11 minutes on two million triples. Its PASS is recorded
in build/gate-pass.txt against the SHA-256 of every input (the tables, the
mapping, the ontology, the shapes, the validator); when none has changed, a
restart skips it. The inputs are hashed, not the graph: Morph-KGC names the
date periods with new blank nodes on every run, so the same data never gives
the same file.
"""

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import rdflib
import requests

# Keep each value exactly as the mapping writes it. By default rdflib rewrites
# "PT25H10M" into "P1DT1H10M" as soon as it creates or reads the value
# (found in Session 4: 13,694 Warnings that were not in the data).
rdflib.NORMALIZE_LITERALS = False

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
GTFS_DIR = ROOT / "data" / "halifax" / "gtfs"
LINKED_GTFS = ROOT / "ontology" / "linked-gtfs-corrected.ttl"
ONTOLOGY = ROOT / "ontology" / "ontology.ttl"
SHAPES = ROOT / "shapes" / "shapes.ttl"
ORDER_SHAPE = ROOT / "shapes" / "trip-order-shape.ttl"
MAPPING = ROOT / "mapping" / "mapping.ttl"
GRAPH = BUILD / "graph.nt"
FUSEKI = os.environ.get("FUSEKI_URL", "http://127.0.0.1:3030")
DATASET = os.environ.get("FUSEKI_DATASET", "kr")
PROV_GRAPH = "https://ul.edu.lb/kr/id/graph/halifax/provenance"
TABLES = ["agency", "feed_info", "routes", "trips", "stops", "stop_times", "calendar", "calendar_dates"]


def step(n, text):
    print(f"{n} {text}", flush=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def source(sample):
    """Step 1. The tables, as text, in SQLite. GTFS ids such as "259.0.1" and
    "10A" are names, not numbers, and a time such as " 5:49:00" keeps its
    stray space: turning text into typed values is the mapping's job."""
    db = BUILD / ("example.sqlite" if sample else "halifax.sqlite")
    db.unlink(missing_ok=True)
    con = sqlite3.connect(db)
    if sample:
        con.executescript((ROOT / "data" / "example.sql").read_text(encoding="utf-8"))
        step(1, "source: the sample, data/example.sql (7 trips)")
    else:
        fetch = subprocess.run([sys.executable, str(ROOT / "data" / "fetch_data.py")], capture_output=True, text=True)
        if fetch.returncode:
            sys.exit(f"Fetching the feed failed:\n{fetch.stdout}{fetch.stderr}")
        for name in TABLES:
            df = pd.read_csv(GTFS_DIR / f"{name}.txt", dtype=str, keep_default_na=False, encoding="utf-8-sig")
            df.to_sql(name, con, if_exists="replace", index=False, chunksize=20_000)
        n = con.execute("SELECT COUNT(*) FROM stop_times").fetchone()[0]
        step(1, f"source: the Halifax feed, SHA-256 checked; 8 tables, {n:,} stop times -> build/halifax.sqlite")
    con.close()
    return db


def materialize(db):
    """Step 2. The R2RML mapping, run by Morph-KGC."""
    import morph_kgc
    t0 = time.time()
    cfg = (f"[CONFIGURATION]\nlogging_level=WARNING\n\n"
           f"[Halifax]\nmappings={MAPPING}\ndb_url=sqlite:///{db}\n")
    graph = morph_kgc.materialize(cfg)
    graph.serialize(GRAPH, format="nt", encoding="utf-8")
    step(2, f"map: {len(graph):,} triples in {time.time() - t0:.0f} s -> build/graph.nt")


def gate_inputs(sample):
    files = [MAPPING, ONTOLOGY, SHAPES, ROOT / "shapes" / "validate.py", Path(__file__)]
    files += [ROOT / "data" / "example.sql", ORDER_SHAPE] if sample else [GTFS_DIR / f"{t}.txt" for t in TABLES]
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in files}


def gate(sample, regate):
    """Step 3. Any Violation stops the pipeline: the endpoint is only ever
    loaded with data that passed. Warnings and Info pass (shapes/triage.md)."""
    inputs = gate_inputs(sample)
    stamp = BUILD / ("gate-pass-sample.txt" if sample else "gate-pass.txt")
    if not regate and stamp.exists():
        recorded = json.loads(stamp.read_text(encoding="utf-8"))
        if recorded["inputs"] == inputs:
            step(3, f"validate: PASS recorded {recorded['passed']} for these exact inputs, not run again "
                    f"(--regate to force): {recorded['summary']}")
            return recorded
    shapes = [SHAPES] + ([ORDER_SHAPE] if sample else [])
    args = ["--data", GRAPH, "--data", ONTOLOGY] + [a for s in shapes for a in ("--shapes", s)]
    if not sample:
        print("  (the whole graph: about 11 minutes)", flush=True)
    p = subprocess.Popen([sys.executable, "validate.py", *map(str, args)], cwd=ROOT / "shapes",
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                         env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    lines = []
    for line in p.stdout:  # shown as it comes
        lines.append(line)
        print("  " + line.rstrip(), flush=True)
    p.wait()
    (BUILD / "shacl-gate.txt").write_text("".join(lines), encoding="utf-8")
    stamp.unlink(missing_ok=True)
    summary = next((l.strip() for l in lines if l.strip().startswith("validated in")), "no summary")
    step(3, f"validate: {summary} -> build/shacl-gate.txt")
    if p.returncode:
        sys.exit("SHACL gate: the data has Violations, so the endpoint is not loaded. Read build/shacl-gate.txt.")
    recorded = {"passed": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "summary": summary, "inputs": inputs}
    stamp.write_text(json.dumps(recorded, indent=1), encoding="utf-8")
    return recorded


def describe():
    """Step 4. The VoID of what the endpoint will hold, not of the graph alone:
    without Linked GTFS, gtfs:Bus has no class and the description loses
    gtfs:RouteType (found on the first deployed run)."""
    sys.path.insert(0, str(ROOT / "access-layer"))
    from make_void import write_void
    n = write_void(GRAPH, BUILD / "void.ttl", [ONTOLOGY, LINKED_GTFS])
    step(4, f"describe: {n} VoID triples -> build/void.ttl")


def provenance(started, gate_record, sample):
    """Step 5. PROV-O: the graph, the files it was derived from with their
    SHA-256, the run, and the gate's verdict."""
    from rdflib import RDF, RDFS, XSD, Graph, Literal, Namespace, URIRef
    PROV, DCT, VOID = (Namespace("http://www.w3.org/ns/prov#"), Namespace("http://purl.org/dc/terms/"),
                       Namespace("http://rdfs.org/ns/void#"))
    ID = "https://ul.edu.lb/kr/id/"
    ended = datetime.now(timezone.utc).replace(microsecond=0)
    g = Graph()
    for p, ns in (("prov", PROV), ("dcterms", DCT), ("void", VOID)):
        g.bind(p, ns)
    graph = URIRef(f"{ID}graph/halifax/deployed")
    run = URIRef(f"{ID}run/halifax/pipeline-{ended.strftime('%Y%m%dT%H%M%SZ')}")
    g.add((graph, RDF.type, PROV.Entity))
    g.add((graph, RDFS.label, Literal("The Halifax graph in the endpoint's default graph")))
    g.add((graph, VOID.triples, Literal(sum(1 for _ in open(GRAPH, "rb")))))
    g.add((graph, PROV.wasGeneratedBy, run))
    g.add((graph, DCT.conformsTo, URIRef("https://ul.edu.lb/kr/transit/1.1.0")))
    g.add((run, RDF.type, PROV.Activity))
    g.add((run, RDFS.label, Literal("pipeline/run.py: source, map, validate, describe, load")))
    g.add((run, PROV.startedAtTime, Literal(started.isoformat(), datatype=XSD.dateTime)))
    g.add((run, PROV.endedAtTime, Literal(ended.isoformat(), datatype=XSD.dateTime)))
    g.add((run, RDFS.comment, Literal("SHACL gate: " + gate_record["summary"])))
    sources = ([ROOT / "data" / "example.sql"] if sample else [GTFS_DIR / f"{t}.txt" for t in TABLES])
    for src in sources + [MAPPING, ONTOLOGY, LINKED_GTFS, SHAPES]:
        f = URIRef(f"{ID}file/halifax/{src.name}")
        g.add((f, RDF.type, PROV.Entity))
        g.add((f, DCT.title, Literal(src.name)))
        g.add((f, DCT.identifier, Literal("sha256:" + sha256(src))))
        g.add((run, PROV.used, f))
        if src in sources:
            g.add((graph, PROV.wasDerivedFrom, f))
    g.serialize(BUILD / "provenance.ttl", format="turtle")
    step(5, f"provenance: {len(sources)} source files and 4 more inputs, with their SHA-256 -> build/provenance.ttl")


def load():
    """Step 6. Replaces what the endpoint held."""
    for _ in range(60):  # the endpoint may still be starting
        try:
            if requests.get(f"{FUSEKI}/$/ping", timeout=5).ok:
                break
        except requests.ConnectionError:
            pass
        time.sleep(2)
    else:
        sys.exit(f"The endpoint at {FUSEKI} did not answer within two minutes.")
    t0 = time.time()
    requests.post(f"{FUSEKI}/{DATASET}/update", data={"update": "DROP ALL"}, timeout=600).raise_for_status()
    uploads = [("default", GRAPH, "application/n-triples"), ("default", ONTOLOGY, "text/turtle"),
               ("default", LINKED_GTFS, "text/turtle"), (f"graph={PROV_GRAPH}", BUILD / "provenance.ttl", "text/turtle")]
    for target, path, ctype in uploads:
        with open(path, "rb") as f:
            r = requests.post(f"{FUSEKI}/{DATASET}/data?{target}", data=f,
                              headers={"Content-Type": ctype}, timeout=1800)
        if not r.ok:
            sys.exit(f"Loading {path.name} failed ({r.status_code}): {r.text[:200]}")
    r = requests.get(f"{FUSEKI}/{DATASET}/sparql", params={"query": "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }"},
                     headers={"Accept": "application/sparql-results+json"}, timeout=120)
    n = int(r.json()["results"]["bindings"][0]["n"]["value"])
    step(6, f"load: {n:,} triples in the default graph, provenance in a named graph, "
            f"in {time.time() - t0:.0f} s -> {FUSEKI}/{DATASET}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-load", action="store_true", help="stop before loading the endpoint")
    ap.add_argument("--sample", action="store_true", help="data/example.sql instead of the whole feed (CI)")
    ap.add_argument("--regate", action="store_true", help="validate even if these inputs passed before")
    a = ap.parse_args()
    BUILD.mkdir(exist_ok=True)
    started = datetime.now(timezone.utc).replace(microsecond=0)
    materialize(source(a.sample))
    record = gate(a.sample, a.regate)
    describe()
    provenance(started, record, a.sample)
    if not a.no_load:
        load()
    print("done", flush=True)


if __name__ == "__main__":
    main()
