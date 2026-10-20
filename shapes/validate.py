"""Validate a graph against SHACL shapes with pySHACL, and print the report
as a work queue: one line per shape and problem, with a count and examples.

Run from shapes/ (pipeline/run.py runs it as the gate):

    python validate.py                                   # build/graph.nt, the gate's shapes
    python validate.py --shapes shapes-v0.ttl            # the first draft
    python validate.py --data ../build/graph.nt --data ../ontology/ontology.ttl --shapes shapes.ttl
                                                         # what the pipeline's gate runs

It works as a gate: the exit code is 1 when any result has severity
Violation, and 0 otherwise. Warnings and Info results are printed but do not
fail the gate (SHACL itself still reports conforms = false for them; see the
"conforms" line). pipeline/run.py runs it, in the stack and in CI
(.github/workflows/shacl-gate.yml).

Before trusting a clean report, read the "focus nodes" lines: a shape whose
target matches nothing checks nothing, and still conforms.
"""

import argparse
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import rdflib
from pyshacl import validate
from rdflib import RDF, RDFS, Graph, Namespace

# Check each value as the file writes it. By default rdflib rewrites a value
# into its own preferred form as soon as it reads it ("PT25H10M" becomes
# "P1DT1H10M"), so a rule about how a value is written would test rdflib,
# not the data.
rdflib.NORMALIZE_LITERALS = False

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = HERE.parent / "build" / "graph.nt"
SH = Namespace("http://www.w3.org/ns/shacl#")
SEVERITY = {SH.Violation: "Violation", SH.Warning: "Warning", SH.Info: "Info"}


def short(node, data=None):
    """A readable name: the kind and key of a data IRI (trip/halifax/4648930
    becomes trip/4648930), or the local name of a vocabulary term."""
    s = str(node)
    if s.startswith("https://ul.edu.lb/kr/id/"):
        kind, _, key = s[len("https://ul.edu.lb/kr/id/"):].partition("/halifax/")
        return f"{kind}/{key}"
    for base in ("http://vocab.gtfs.org/terms#", "https://ul.edu.lb/kr/transit#",
                 "https://ul.edu.lb/kr/transit/shapes#"):
        if s.startswith(base):
            return s[len(base):]
    return s.rsplit("#", 1)[-1]


def node_shape_of(shapes, shape):
    """The node shape a result belongs to (a property shape's parent)."""
    parent = shapes.value(predicate=SH.property, object=shape)
    return parent if parent is not None else shape


def focus_counts(data, shapes):
    """How many nodes each node shape targets (sh:targetClass, with subclasses)."""
    out = {}
    for ns in set(shapes.subjects(RDF.type, SH.NodeShape)):
        n = 0
        for cls in shapes.objects(ns, SH.targetClass):
            subs = set(data.transitive_subjects(RDFS.subClassOf, cls))
            n += len({s for c in subs for s in data.subjects(RDF.type, c)})
        for node in shapes.objects(ns, SH.targetNode):
            n += 1
        out[ns] = n
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", action="append", help="data file (repeat to merge several)")
    ap.add_argument("--shapes", action="append", help="shapes file (repeat to merge several); "
                    "default shapes.ttl")
    ap.add_argument("--report", help="also write the full SHACL report (Turtle) to this file")
    ap.add_argument("--examples", type=int, default=3, help="focus nodes shown per line")
    args = ap.parse_args()

    data = Graph()
    for f in args.data or [str(DEFAULT_DATA)]:
        if not Path(f).exists():
            sys.exit(f"{f} not found. Run python pipeline/run.py --no-load first.")
        data.parse(f)
    shape_files = args.shapes or [str(HERE / "shapes.ttl")]
    shapes = Graph()
    for f in shape_files:
        shapes.parse(f)
    print(f"data: {len(data):,} triples from {', '.join(Path(f).name for f in (args.data or [DEFAULT_DATA]))}")
    print(f"shapes: {', '.join(Path(f).name for f in shape_files)}")

    labels = {s: str(shapes.value(s, RDFS.label) or short(s)) for s in shapes.subjects(RDF.type, SH.NodeShape)}
    for ns, n in sorted(focus_counts(data, shapes).items(), key=lambda kv: labels[kv[0]]):
        flag = "   <- targets nothing: this shape checks nothing" if n == 0 else ""
        print(f"  focus nodes {n:>6,}  {labels[ns]}{flag}")

    t0 = time.time()
    # inplace: validate the graph as loaded, without pySHACL's own copy of it
    # (two million triples take about 15 s to copy). Nothing is added to it:
    # no inference, and no SHACL rules in these shapes.
    conforms, report, _ = validate(data, shacl_graph=shapes, inference="none", advanced=True, inplace=True)
    secs = time.time() - t0

    groups = defaultdict(list)
    for r in report.subjects(RDF.type, SH.ValidationResult):
        sev = SEVERITY.get(report.value(r, SH.resultSeverity), "?")
        src = report.value(r, SH.sourceShape)
        comp = short(report.value(r, SH.sourceConstraintComponent)).replace("ConstraintComponent", "")
        path = report.value(r, SH.resultPath)
        what = f"{comp} on {short(path)}" if path is not None else comp
        groups[(sev, labels.get(node_shape_of(shapes, src), short(src)), what)].append(report.value(r, SH.focusNode))

    by_sev = Counter()
    for (sev, _, _), nodes in groups.items():
        by_sev[sev] += len(nodes)
    print(f"\nvalidated in {secs:.1f} s. conforms (SHACL): {conforms}. "
          + ", ".join(f"{by_sev[s]:,} {s}" for s in ("Violation", "Warning", "Info")))
    order = {"Violation": 0, "Warning": 1, "Info": 2}
    for (sev, shape, what), nodes in sorted(groups.items(), key=lambda kv: (order.get(kv[0][0], 3), -len(kv[1]))):
        ex = ", ".join(short(n, data) for n in sorted(nodes, key=str)[: args.examples])
        print(f"  {sev:<9} {len(nodes):>6,}  {shape} | {what}   e.g. {ex}")

    if args.report:
        report.serialize(args.report, format="turtle")
        print(f"\nfull report written to {args.report}")

    if by_sev["Violation"]:
        print(f"\nGATE: FAIL, {by_sev['Violation']:,} violations. Exit code 1.")
        sys.exit(1)
    print("\nGATE: PASS, no violations" + (" (warnings are listed above)." if by_sev["Warning"] else "."))


if __name__ == "__main__":
    main()
