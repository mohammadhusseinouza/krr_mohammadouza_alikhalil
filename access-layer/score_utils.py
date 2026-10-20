"""How TEXT2SPARQL scores one answer, in a few lines: every value the query
returns goes into one set, and that set is compared with the right query's."""


def answer_set(rows):
    """All values of all variables of all rows, as one set of strings (ASK: {'true'} or {'false'})."""
    if rows is None:
        return set()
    if isinstance(rows, bool):
        return {"true" if rows else "false"}
    return {v for row in rows for v in row.values()}


def set_precision(pred, gold):
    """Of the values the query returned, the share that are right."""
    return len(pred & gold) / len(pred) if pred else 0.0


def set_recall(pred, gold):
    """Of the right values, the share the query returned."""
    return len(pred & gold) / len(gold) if gold else 0.0


def set_f1(pred, gold):
    p, r = set_precision(pred, gold), set_recall(pred, gold)
    return 2 * p * r / (p + r) if p + r else 0.0
