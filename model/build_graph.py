"""Turn the Halifax graph into the shape a graph neural network reads: one
table of features per kind of node, one list of links per kind of edge
(PyTorch Geometric's HeteroData).

    python build_graph.py

Run from model/, after the pipeline has written ../build/graph.nt (the
deployed graph, mapped from the feed: python pipeline/run.py --no-load).
About 25 s. Writes data/halifax-graph.pt.

The label to predict, "is this a night trip?", is in the graph THREE times:
as the class tr:NightTrip, as the missing class gtfs:Trip (Session 2 and the
mapping type a night trip tr:NightTrip only), and in the times of its stop
times, one of which reaches 24:00:00. None of them reaches the model: no
type is a feature, and no clock time is either. The label is kept apart, in
y. Leave a time in and any model scores perfectly, and learns nothing
(baseline.py shows it).
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import rdflib
import torch
from rdflib import RDF, Graph, Namespace
from rdflib.plugins.parsers.ntriples import W3CNTriplesParser
from torch_geometric.data import HeteroData

HERE = Path(__file__).resolve().parent
SOURCES = [HERE.parent / "build" / "graph.nt"]
OUT = HERE / "data" / "halifax-graph.pt"
GTFS = Namespace("http://vocab.gtfs.org/terms#")
TR = Namespace("https://ul.edu.lb/kr/transit#")
GEO = Namespace("http://www.w3.org/2003/01/geo/wgs84_pos#")
# Each trip links to one thing of each of these kinds. gtfs:block is a number
# in the graph, not an IRI; it becomes a node here because the trips that
# share it share one vehicle's working day.
TRIP_LINKS = [(GTFS.route, "route"), (GTFS.service, "service"), (GTFS.shape, "shape"), (GTFS.block, "block")]
STOP_TIME = [GTFS.trip, GTFS.stop, GTFS.stopSequence, GTFS.arrivalTime, GTFS.departureTime]
KEEP = {RDF.type, GTFS.direction, GEO.lat, GEO.long, *STOP_TIME, *(p for p, _ in TRIP_LINKS)}

# Keep each value as the graph writes it (Session 5, materialize.py); the
# durations are read by value below, so either text of 25:10:00 works.
rdflib.NORMALIZE_LITERALS = False


class Keep:
    """Receives the triples one at a time from the N-Triples parser and keeps
    only the properties the model needs: two million triples never sit in
    one rdflib Graph."""

    def __init__(self):
        self.facts = defaultdict(dict)  # subject -> {property: value}
        self.types = defaultdict(set)

    def triple(self, s, p, o):
        if p == RDF.type:
            self.types[s].add(o)
        elif p in KEEP:
            self.facts[s][p] = o


def read(src):
    keep = Keep()
    if src.suffix == ".nt":
        with open(src, "rb") as f:
            W3CNTriplesParser(keep).parse(f)
    else:
        for s, p, o in Graph().parse(src, format="turtle"):
            keep.triple(s, p, o)
    return keep


def hours(duration):
    """An xsd:duration since the start of the service day, in hours."""
    return duration.value.total_seconds() / 3600


def main():
    src = next((p for p in SOURCES if p.exists()), None)
    if src is None:
        sys.exit("No graph found: run python pipeline/run.py --no-load from the repository root first.")
    t0 = time.time()
    g = read(src)
    n_triples = sum(len(v) for v in g.facts.values()) + sum(len(v) for v in g.types.values())
    trips = sorted((s for s, t in g.types.items() if GTFS.Trip in t or TR.NightTrip in t), key=str)

    # The label, kept apart. It comes from the class; the times say the same.
    y = np.array([1 if TR.NightTrip in g.types[t] else 0 for t in trips])

    # Each trip's stop times, in order: (sequence, stop, arrival, departure).
    calls = defaultdict(list)
    for s, f in g.facts.items():
        if GTFS.trip in f:
            calls[f[GTFS.trip]].append((int(f[GTFS.stopSequence]), f[GTFS.stop],
                                        hours(f[GTFS.arrivalTime]), hours(f[GTFS.departureTime])))
    for c in calls.values():
        c.sort()

    # rdflib does not guarantee iteration order. Node IDs sorted by name and
    # edges in trip order make the fixed training seeds reproducible.
    names = {kind: sorted({str(g.facts[t][prop]) for t in trips}) for prop, kind in TRIP_LINKS}
    names["stop"] = sorted({str(c[1]) for t in trips for c in calls[t]})
    ids = {"trip": {str(t): i for i, t in enumerate(trips)}}
    ids.update({kind: {n: i for i, n in enumerate(table)} for kind, table in names.items()})

    edges = defaultdict(list)
    nexts = set()
    for i, t in enumerate(trips):
        for prop, kind in TRIP_LINKS:
            edges["trip", str(prop).split("#")[1], kind].append((i, ids[kind][str(g.facts[t][prop])]))
        stops = [ids["stop"][str(c[1])] for c in calls[t]]
        # A stop time links one trip to one stop: the graph says it in two
        # hops (trip <- stop time -> stop); the model gets one edge per stop.
        edges["trip", "callsAt", "stop"].extend((i, s) for s in dict.fromkeys(stops))
        nexts.update((a, b) for a, b in zip(stops, stops[1:]) if a != b)
    edges["stop", "next", "stop"] = sorted(nexts)

    # What the model may see about a trip: how many stops, how long, which
    # direction. NOT the type, and NOT a clock time: that would be the answer.
    n_stops = np.array([len(calls[t]) for t in trips])
    minutes = np.array([60 * (calls[t][-1][2] - calls[t][0][3]) for t in trips])
    direction = np.array([1.0 if str(g.facts[t][GTFS.direction]) in ("true", "1") else 0.0 for t in trips])
    x = np.column_stack([np.log1p(n_stops), np.log1p(minutes), direction])

    # What the model may see about a stop: where it is.
    pos = np.array([[float(g.facts[rdflib.URIRef(s)][GEO.lat]), float(g.facts[rdflib.URIRef(s)][GEO.long])]
                    for s in names["stop"]])

    data = HeteroData()
    data["trip"].x = torch.tensor(x, dtype=torch.float)
    data["stop"].x = torch.tensor((pos - pos.mean(0)) / pos.std(0), dtype=torch.float)
    for kind, table in names.items():
        if kind != "stop":
            data[kind].x = torch.eye(len(table))  # one column per node: "which one is it"
    for (s, r, t), pairs in edges.items():
        data[s, r, t].edge_index = torch.tensor(np.array(pairs).T, dtype=torch.long).contiguous()

    of = lambda kind, prop: torch.tensor([ids[kind][str(g.facts[t][prop])] for t in trips])
    extra = {
        "y": torch.tensor(y),
        # kept ONLY for the leak demos: the hour of a trip's last and first stop
        "last_hour": torch.tensor([max(c[2] for c in calls[t]) for t in trips]),
        "first_hour": torch.tensor([calls[t][0][3] for t in trips]),
        "route": of("route", GTFS.route),
        "service": of("service", GTFS.service),
        "block": of("block", GTFS.block),
        "trip_iri": [str(t) for t in trips],
        "names": names,
        "source": src.name,
    }
    OUT.parent.mkdir(exist_ok=True)
    torch.save({"data": data, **extra}, OUT)

    print(f"read {src.name}: kept {n_triples:,} triples in {time.time() - t0:.1f} s")
    print("nodes: " + ", ".join(f"{k} {len(v):,}" for k, v in ids.items()))
    print("edges: " + ", ".join(f"{r} {len(p):,}" for (_, r, _), p in edges.items()))
    print(f"label: {int(y.sum())} night trips of {len(y):,} ({y.mean():.1%}), taken out of the features "
          "(the classes tr:NightTrip and gtfs:Trip, and every clock time)")
    print(f"written: {OUT.relative_to(HERE).as_posix()}")


if __name__ == "__main__":
    main()
