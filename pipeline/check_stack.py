"""Is the deployed stack really working? One check per layer, against the
running containers, the way the instructor checks it from a clean checkout.

    python pipeline/check_stack.py              all checks; the last two ask the model (2 calls)
    python pipeline/check_stack.py --no-model   only the checks that need no model call

Run from the repository root (needs only requests), after `docker compose up
--build` has printed that the access layer is serving.
Every check prints PASS or FAIL; the exit code is the number of FAILs.
"""

import argparse
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
SPARQL = "http://127.0.0.1:3030/kr/sparql"
LAYER = "http://127.0.0.1:8000/"
DATASET = "https://ul.edu.lb/kr/halifax/"
VERSION_IRI = "https://ul.edu.lb/kr/transit/1.1.0"
PREFIXES = """PREFIX gtfs: <http://vocab.gtfs.org/terms#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX dcterms: <http://purl.org/dc/terms/>
"""
fails = 0


def sparql(query, prefixes=PREFIXES):
    r = requests.get(SPARQL, params={"query": prefixes + query},
                     headers={"Accept": "application/sparql-results+json"}, timeout=120)
    r.raise_for_status()
    body = r.json()
    if "boolean" in body:
        return body["boolean"]
    return [{k: v["value"] for k, v in row.items()} for row in body["results"]["bindings"]]


def check(name, ok, detail):
    global fails
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {detail}")


def one(query):
    return int(next(iter(sparql(query)[0].values())))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-model", action="store_true", help="skip the two checks that call the model")
    no_model = ap.parse_args().no_model

    print("Gate (Session 4)")
    stamp = ROOT / "build" / "gate-pass.txt"
    if stamp.exists():
        rec = json.loads(stamp.read_text(encoding="utf-8"))
        check("SHACL gate", "0 Violation" in rec["summary"], f"{rec['summary']} (passed {rec['passed']})")
    else:
        check("SHACL gate", False, "no build/gate-pass.txt: the pipeline has not passed the gate")

    print("Endpoint (Session 2)")
    try:
        n = one("SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }")
    except requests.ConnectionError:
        check("Fuseki", False, f"nothing answers at {SPARQL}: is the stack up?")
        sys.exit(fails)
    check("triples in the default graph", n > 2_000_000, f"{n:,}")
    trips = one("SELECT (COUNT(?t) AS ?n) WHERE { ?t gtfs:route <https://ul.edu.lb/kr/id/route/halifax/1> }")
    check("trips on route 1", trips == 496, f"{trips} (Session 2: 496)")
    plain = one("SELECT (COUNT(?t) AS ?n) WHERE { ?t a gtfs:Trip }")
    every = one("SELECT (COUNT(DISTINCT ?t) AS ?n) WHERE { ?t a/rdfs:subClassOf* gtfs:Trip }")
    check("the night trip trap", (plain, every) == (9022, 9239),
          f"a gtfs:Trip finds {plain:,}, with subclasses {every:,} (Session 2: 9,022 and 9,239)")

    print("Ontology (Session 3)")
    has = sparql(f"ASK {{ ?o owl:versionIRI <{VERSION_IRI}> }}")
    check("ontology release", has, f"the endpoint {'holds' if has else 'lacks'} release <{VERSION_IRI}>")

    print("Provenance (Session 4)")
    rows = sparql("""SELECT ?file ?sha WHERE { GRAPH ?g {
        <https://ul.edu.lb/kr/id/graph/halifax/deployed> prov:wasDerivedFrom ?f .
        ?f dcterms:title ?file ; dcterms:identifier ?sha } } ORDER BY ?file""")
    check("where the deployed graph comes from", len(rows) == 8,
          f"{len(rows)} source files with their SHA-256, e.g. " +
          (f"{rows[0]['file']} {rows[0]['sha'][:19]}..." if rows else "none"))

    print("Access layer (Session 7)")
    try:
        requests.get(LAYER, timeout=5)
    except requests.ConnectionError:
        check("serve.py", False, f"nothing answers at {LAYER}")
        sys.exit(fails)
    if no_model:
        print("  skipped: one question and one refusal (--no-model)")
        sys.exit(fails)
    q = requests.get(LAYER, params={"question": "How many trips run on route 1?", "dataset": DATASET},
                     timeout=300).json()["query"]
    rows = sparql(q, prefixes="")  # the layer's query declares its own prefixes; run it as given
    values = [v for row in rows for v in row.values()]
    check("one question", "496" in values, f"How many trips run on route 1? -> {values[:3]}")
    q = requests.get(LAYER, params={"question": "Which stops are wheelchair accessible?", "dataset": DATASET},
                     timeout=300).json()["query"]
    refused = q.startswith("# ") and "FILTER(false)" in q
    check("one refusal", refused, q.splitlines()[0] if refused else "answered instead of refusing")
    sys.exit(fails)


if __name__ == "__main__":
    main()
