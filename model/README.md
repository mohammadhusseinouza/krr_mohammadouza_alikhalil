# model/

Learning over the graph (Session 6). Not served by the stack: the rubric
scores the results and how honestly they were measured.

```sh
python -m pip install -r model/requirements-model.txt
python pipeline/run.py --no-load        # from the root: writes build/graph.nt
cd model
python build_graph.py                   # the graph as PyTorch Geometric data, label held out
python baseline.py                      # leaks, then the baselines
python gnn.py                           # a graph neural network, several seeds
python link_prediction.py               # TransE against two baselines, several seeds
python tie_check.py                     # the baselines under four tie protocols (seconds)
```

Every recorded run is in `results/`, with its date and versions. They were
made on Session 5's mapped graph, which is the graph `build/graph.nt` holds
(the same mapping over the same feed).

## Node classification: is this trip a night trip?

217 of 9,239 trips (2.3%) run past midnight. **Night is a clock fact**, so
the label is hidden in three places: the class `tr:NightTrip`, the missing
`gtfs:Trip` type (a night trip is typed `tr:NightTrip` only), and every
clock time. The model sees how many stops, how many minutes, which
direction, and the route, block and stops, never a time.

| Run | PR-AUC |
|---|---|
| Leak: the last stop's hour | 0.996 |
| Leak: the first stop's hour | 0.989 |
| Guessing | 0.023 |
| Baseline, random split | 0.102 |
| Baseline, split by route | 0.022 to 0.043 |
| GNN, random split | 0.045 to 0.094 |
| GNN, split by route | 0.021 to 0.031 |

**The split by route** keeps every trip of a route on one side, so a model
cannot pass by remembering routes; it falls to guessing. **The GNN loses to
the baseline**, and that is the result: with the clock removed, the graph
does not say which trip of a route runs late. A split by time would need a
second dated feed.

## Link prediction: which route serves this stop?

5,160 serves links (81 routes). The trips are left out (a trip on a route
calling at a stop *is* the link), and so are the shapes (a shape belongs to
one route: with them, TransE goes from 0.185 to 0.410 on seed 0).

| Model | MRR |
|---|---|
| Popularity | about 0.11 |
| TransE | 0.159 to 0.197 |
| Neighbour count | 0.871 to 0.889 |

**The second baseline** (rank routes by how many of the stop's neighbours
they serve) is what keeps this honest: against popularity alone, TransE
would have looked like a win.

**The tie protocol** (`tie_check.py`, `results/tie-check.txt`): the ranking
keeps tied routes in list order. Re-scored with the true route first, last
and at random among its ties, the neighbour count stays at 0.871 to 0.889
under the most pessimistic protocol (ties on 12 to 20 of 516 links), and
popularity between 0.103 and 0.118. The report's Section 9 explains why
this check matters.
