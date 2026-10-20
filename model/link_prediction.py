"""Link prediction: which route serves this stop? A knowledge graph
embedding (TransE, with PyKEEN) against two simple baselines: "guess the
route that serves the most stops", and "guess the routes that serve the
stops next to it".

    python link_prediction.py

Run from model/ after build_graph.py. Under a minute.

The question: hide 10% of the "route serves stop" links, learn from the
rest, and for each hidden link rank the 81 routes from most to least likely.
Scores are "filtered": other routes already known to serve that stop do not
count against the model. "Route serves stop" is not a triple in the graph:
it is read from the trips (a trip has a route and calls at stops). TransE
learns from it and from one more kind of link: which stop comes next after
which, on any trip.
The trips themselves are left out on purpose: "trip on route" and "trip
calls at stop" together ARE the serves link, so they would give the answer
away. So are the shapes: a shape belongs to one route.
"""

import collections
import os
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
# PyKEEN uses PyStow for its cache.  Keep that cache with the generated lab
# data instead of assuming every student can write to a home-directory default
# such as ~/.data (often false on managed lab computers).
os.environ.setdefault("PYSTOW_HOME", str(HERE / "data" / "pystow"))

from pykeen.pipeline import pipeline
from pykeen.triples import TriplesFactory

from learning_utils import mrr

SEEDS = range(3)


def triples(b):
    names, d = b["names"], b["data"]
    name = lambda kind, i: kind + "/" + names[kind][i].rsplit("/", 1)[-1]
    route_of = d["trip", "route", "route"].edge_index[1].tolist()
    trip, stop = d["trip", "callsAt", "stop"].edge_index.tolist()
    serves = sorted({(name("route", route_of[t]), "serves", name("stop", s)) for t, s in zip(trip, stop)})
    other = sorted((name("stop", a), "next", name("stop", c)) for a, c in d["stop", "next", "stop"].edge_index.T.tolist())
    return serves, other


def ranks_among_routes(score, test, known, routes):
    """Rank the true route among all routes, filtered; returns one rank per test link."""
    out = []
    for h, _, t in test:
        cand = [r for r in routes if r == h or r not in known[t]]
        order = sorted(cand, key=lambda r: -score(r, t))
        out.append(order.index(h) + 1)
    return out


def main():
    b = torch.load(HERE / "data" / "halifax-graph.pt", weights_only=False)
    serves, other = triples(b)
    routes = sorted({h for h, _, _ in serves})
    known = collections.defaultdict(set)
    for h, _, t in serves:
        known[t].add(h)
    nbrs = collections.defaultdict(set)  # the stops just before or after a stop, on any trip
    for a, _, c in other:
        nbrs[a].add(c)
        nbrs[c].add(a)
    print(f"{len(serves):,} serves links ({len(routes)} routes), {len(other):,} next links")
    for seed in SEEDS:
        rng = np.random.RandomState(seed)
        perm = rng.permutation(len(serves))
        n = len(serves) // 10
        test, valid, train = [serves[i] for i in perm[:n]], [serves[i] for i in perm[n:2 * n]], [serves[i] for i in perm[2 * n:]]
        tf = TriplesFactory.from_labeled_triples(np.array(train + other))
        seen = lambda L: [x for x in L if x[0] in tf.entity_to_id and x[2] in tf.entity_to_id]
        cold = len(test) - len(seen(test))
        test, valid = seen(test), seen(valid)
        mk = lambda L: TriplesFactory.from_labeled_triples(np.array(L), entity_to_id=tf.entity_to_id, relation_to_id=tf.relation_to_id)
        result = pipeline(training=tf, validation=mk(valid), testing=mk(test), model="TransE",
                          model_kwargs=dict(embedding_dim=32), training_kwargs=dict(num_epochs=150, batch_size=512),
                          random_seed=seed, device="cpu", use_tqdm=False)
        model, ent, rel = result.model, tf.entity_to_id, tf.relation_to_id["serves"]
        with torch.no_grad():
            cache = {}
            def transe(r, t):
                if t not in cache:
                    cache[t] = model.score_h(torch.tensor([[rel, ent[t]]]))[0]
                return float(cache[t][ent[r]]) if r in ent else float("-inf")  # a route never seen in training ranks last
            r_model = ranks_among_routes(transe, test, known, routes)
        popular = collections.Counter(h for h, _, _ in train)
        r_pop = ranks_among_routes(lambda r, t: popular.get(r, 0), test, known, routes)
        # The neighbour count: how many of the stop's neighbours the route is
        # known (in training) to serve; popularity breaks ties.
        served = collections.defaultdict(set)
        for h, _, t in train:
            served[t].add(h)
        near = lambda r, t: sum(r in served[s] for s in nbrs[t]) + popular.get(r, 0) / (1 + len(train))
        r_near = ranks_among_routes(near, test, known, routes)
        hits1 = lambda r: float(np.mean(np.asarray(r) == 1))
        print(f"seed {seed}: {len(test)} hidden links scored ({cold} left out: their stop appears in no other link)")
        print(f"  TransE      MRR {mrr(r_model):.3f}  Hits@1 {hits1(r_model):.3f}")
        print(f"  popularity  MRR {mrr(r_pop):.3f}  Hits@1 {hits1(r_pop):.3f}")
        print(f"  neighbours  MRR {mrr(r_near):.3f}  Hits@1 {hits1(r_near):.3f}")


if __name__ == "__main__":
    main()
