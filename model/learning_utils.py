"""Small helpers every Session 6 script uses: how to split the trips, and
how to score a ranking. Read them: Part B asks you to write three more in
exactly the same style (my_learning.py).
"""

import numpy as np


# ---------------------------------------------------------------- splits
def split_random(n_trips, y, test_share=0.3, seed=0):
    """Put a random 30% of the trips in the test set, with the same share of
    night trips on both sides (a "stratified" split). Returns (train, test),
    two arrays of trip positions."""
    rng = np.random.RandomState(seed)
    test = []
    for label in (0, 1):
        idx = np.flatnonzero(y == label)
        rng.shuffle(idx)
        test.extend(idx[: int(round(test_share * len(idx)))])
    test = np.sort(np.array(test))
    train = np.setdiff1d(np.arange(n_trips), test)
    return train, test


def split_by_route(route, test_share=0.3, seed=0):
    """Put about 30% of the ROUTES in the test set, with all their trips.
    No route has trips on both sides, so a model cannot pass the test by
    remembering routes. Returns (train, test), arrays of trip positions."""
    rng = np.random.RandomState(seed)
    groups = np.unique(route)
    rng.shuffle(groups)
    test_groups = groups[: int(round(test_share * len(groups)))]
    test = np.flatnonzero(np.isin(route, test_groups))
    train = np.flatnonzero(~np.isin(route, test_groups))
    return train, test


# ---------------------------------------------------------------- scores
def precision_at_k(y_true, scores, k=100):
    """Of the k trips the model ranks most likely night trips, the share that were."""
    top = np.argsort(-np.asarray(scores), kind="stable")[:k]
    return float(np.asarray(y_true)[top].mean())


def mrr(ranks):
    """Mean reciprocal rank: the average of 1/rank of the right answer.
    Rank 1 counts 1, rank 2 counts 0.5, rank 10 counts 0.1."""
    return float(np.mean(1.0 / np.asarray(ranks, dtype=float)))
