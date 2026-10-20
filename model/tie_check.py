"""Do the link prediction baselines survive a fair tie protocol? (report, Section 9)

    python tie_check.py

Run from model/ after build_graph.py. A few seconds; no model is trained.

link_prediction.py ranks the routes with Python's sorted(), which keeps tied
routes in list order, so where the true route lands among its ties depends
on its name. Sun and others (ACL 2020) showed that reported gains in
knowledge graph completion can come from exactly this: how an evaluation
ranks the true answer among candidates with the same score. This script
re-scores the two baselines, on the same three splits, under four protocols:

  as reported  list order, what link_prediction.py does
  top          the true route first among its ties (the most optimistic)
  bottom       the true route last among its ties (the most pessimistic)
  random       a random place among its ties (the protocol Sun and others propose)

TransE is left out: its scores are floating point numbers and do not tie.
"""

import collections

import numpy as np
import torch

from learning_utils import mrr
from link_prediction import HERE, SEEDS, triples


def ranks(score, test, known, routes, protocol, rng):
    out, tied_links = [], 0
    for h, _, t in test:
        cand = [r for r in routes if r == h or r not in known[t]]
        if protocol == "as reported":
            out.append(sorted(cand, key=lambda r: -score(r, t)).index(h) + 1)
            continue
        s = score(h, t)
        better = sum(score(r, t) > s for r in cand)
        ties = sum(score(r, t) == s for r in cand) - 1
        tied_links += ties > 0
        out.append(better + 1 + {"top": 0, "bottom": ties, "random": rng.randint(0, ties + 1)}[protocol])
    return out, tied_links


def main():
    b = torch.load(HERE / "data" / "halifax-graph.pt", weights_only=False)
    serves, other = triples(b)
    routes = sorted({h for h, _, _ in serves})
    known = collections.defaultdict(set)
    for h, _, t in serves:
        known[t].add(h)
    nbrs = collections.defaultdict(set)
    for a, _, c in other:
        nbrs[a].add(c)
        nbrs[c].add(a)
    print(f"{len(serves):,} serves links, {len(routes)} routes; the same splits as link_prediction.py")
    for seed in SEEDS:
        perm = np.random.RandomState(seed).permutation(len(serves))
        n = len(serves) // 10
        test, train = [serves[i] for i in perm[:n]], [serves[i] for i in perm[2 * n:]]
        seen = {x for h, _, t in train + other for x in (h, t)}  # as PyKEEN's entity list
        test = [x for x in test if x[0] in seen and x[2] in seen]
        popular = collections.Counter(h for h, _, _ in train)
        served = collections.defaultdict(set)
        for h, _, t in train:
            served[t].add(h)
        baselines = {
            "popularity": lambda r, t: popular.get(r, 0),
            "neighbours": lambda r, t: sum(r in served[s] for s in nbrs[t]) + popular.get(r, 0) / (1 + len(train)),
        }
        print(f"\nseed {seed}: {len(test)} hidden links")
        for name, score in baselines.items():
            line, tied = [], 0
            for protocol in ("as reported", "top", "bottom", "random"):
                r, t = ranks(score, test, known, routes, protocol, np.random.RandomState(seed))
                tied = max(tied, t)
                line.append(f"{protocol} {mrr(r):.3f}")
            print(f"  {name:<11} MRR  " + "  ".join(line) + f"   ({tied} of {len(test)} links have a tie)")


if __name__ == "__main__":
    main()
