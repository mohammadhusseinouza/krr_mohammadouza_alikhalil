"""Check a query before running it: is it SPARQL, and does it use only terms
the graph has (read from void.ttl)?

    python check.py broken.sparql
    python check.py my_query.sparql
"""
import sys
from pathlib import Path

from access_layer import check_query


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "broken.sparql")
    query = "\n".join(l for l in path.read_text().splitlines() if not l.lstrip().startswith("#"))
    problems = check_query(query)
    print(f"{path.name}: {len(problems)} problem{'s' if len(problems) != 1 else ''}")
    for p in problems:
        print(f"  - {p}")


if __name__ == "__main__":
    main()
