"""Ask the graph one question in English.

    python ask.py "How many trips run on route 1?"
    python ask.py --no-repair "..."        one try only, no repair

Prints each query the model wrote, the problems the check found in it, and
then the rows (the answer and its evidence), or the refusal.
"""
import sys

from access_layer import answer, load_examples, model_name, open_store


def show(question, result):
    print(f"question: {question}")
    for i, a in enumerate(result["attempts"], 1):
        print(f"\ntry {i}:\n{a['query']}")
        print("  problems: " + ("none" if not a["problems"] else "; ".join(p[:110] for p in a["problems"])))
    if result["refused"]:
        print(f"\nrefused: {result['refused']}")
        return
    rows = result["rows"]
    if isinstance(rows, bool):
        print(f"\nanswer: {rows}")
        return
    print(f"\nanswer: {len(rows)} row{'s' if len(rows) != 1 else ''}")
    for row in rows[:10]:
        print("  " + "  ".join(f"{k}={v.rsplit('/', 1)[-1]}" for k, v in row.items()))
    if len(rows) > 10:
        print(f"  ... {len(rows) - 10} more")


def main():
    args = sys.argv[1:]
    repair = "--no-repair" not in args
    question = " ".join(a for a in args if a != "--no-repair") or "How many trips run on route 1?"
    print(f"model: {model_name()}")
    show(question, answer(question, open_store(), load_examples(), repair=repair))


if __name__ == "__main__":
    main()
