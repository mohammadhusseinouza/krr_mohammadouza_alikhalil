"""The baseline: a plain logistic regression on the flattened trip row, the
model any graph model must beat. Four runs, one line each (run 4 five times):

  1. the last stop's hour kept       (the leak: the answer is in the input)
  2. the first stop's hour kept      (a quieter leak: it nearly decides the answer)
  3. a random split of the trips
  4. a split by route                (test routes never seen in training)

    python baseline.py

Run from model/ after build_graph.py. About 10 seconds.

The flattened row is what a table gives: the trip's number of stops,
scheduled minutes and direction, and which route, service and block it has
(one column per possible value, "one-hot"). Scores: PR-AUC (1.0 is perfect,
and a model that guesses scores the share of night trips, 0.023 here),
ROC-AUC (0.5 is guessing) and precision at 100 (of the 100 trips ranked most
likely night trips, the share that were). Accuracy is printed too, to show
why it is useless when only 2% of trips are night trips.
"""

from pathlib import Path

import numpy as np
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, average_precision_score, roc_auc_score
from sklearn.preprocessing import OneHotEncoder

from learning_utils import precision_at_k, split_by_route, split_random

HERE = Path(__file__).resolve().parent
SEEDS = range(5)


def load():
    b = torch.load(HERE / "data" / "halifax-graph.pt", weights_only=False)
    ids = np.column_stack([b["route"], b["service"], b["block"]])
    return b["data"]["trip"].x.numpy(), ids, b, b["y"].numpy(), b["route"].numpy()


def fit_score(x, ids, y, train, test, extra=None):
    onehot = OneHotEncoder(handle_unknown="ignore").fit(ids[train])
    def rows(i):
        parts = [onehot.transform(ids[i]).toarray(), x[i]]
        return np.hstack(parts + ([extra[i, None]] if extra is not None else []))
    model = LogisticRegression(max_iter=2000, class_weight="balanced").fit(rows(train), y[train])
    p = model.predict_proba(rows(test))[:, 1]
    yt = y[test]
    return {"night in test": int(yt.sum()), "PR-AUC": average_precision_score(yt, p) if yt.sum() else float("nan"),
            "ROC-AUC": roc_auc_score(yt, p) if 0 < yt.sum() < len(yt) else float("nan"),
            "precision@100": precision_at_k(yt, p, 100), "accuracy": accuracy_score(yt, p > 0.5)}


def line(name, r):
    if r["night in test"] == 0:
        return f"{name:<36} night in test   0  no night trip in the test set: nothing to measure"
    return (f"{name:<36} night in test {r['night in test']:>3}  PR-AUC {r['PR-AUC']:.3f}  ROC-AUC {r['ROC-AUC']:.3f}  "
            f"precision@100 {r['precision@100']:.2f}  accuracy {r['accuracy']:.3f}")


def main():
    x, ids, b, y, route = load()
    print(f"{len(y):,} trips, {int(y.sum())} night trips ({y.mean():.1%}). Guessing scores PR-AUC {y.mean():.3f}; "
          f"\"never a night trip\" scores accuracy {1 - y.mean():.3f}.\n")
    train, test = split_random(len(y), y)
    print(line("1. random split, last hour kept", fit_score(x, ids, y, train, test, extra=b["last_hour"].numpy())))
    print(line("2. random split, first hour kept", fit_score(x, ids, y, train, test, extra=b["first_hour"].numpy())))
    print(line("3. random split", fit_score(x, ids, y, train, test)))
    for s in SEEDS:
        train, test = split_by_route(route, seed=s)
        print(line(f"4. split by route, seed {s}", fit_score(x, ids, y, train, test)))
    night_routes = np.unique(route[y == 1])
    print(f"\n{len(night_routes)} of {len(np.unique(route))} routes have a night trip. "
          "A split by route puts about 30% of the routes, and their night trips, in the test set.")


if __name__ == "__main__":
    main()
