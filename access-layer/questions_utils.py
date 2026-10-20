"""Read a questions file (TEXT2SPARQL layout plus this course's gold and refuse fields)."""
from pathlib import Path

from ruamel.yaml import YAML


def load_questions(path):
    data = YAML(typ="safe").load(Path(path).read_text())
    prefix = (data.get("dataset") or {}).get("prefix", "")
    out = []
    for q in data["questions"]:
        out.append({"id": q["id"], "question": q["question"]["en"],
                    "gold": (prefix + "\n" + q["gold"]) if q.get("gold") else None,
                    "refuse": q.get("refuse")})
    return out
