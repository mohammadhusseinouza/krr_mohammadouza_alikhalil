"""Run the HermiT reasoner on the ontology, fully offline (Session 3's local_reasoner.py).

Protégé and ROBOT find the imported vocabulary (Linked GTFS, as published
or corrected) through ontology/catalog-v001.xml. This module does the
same by hand: it follows every owl:imports through that catalog, merges
everything into one graph, and hands it to HermiT (bundled with owlready2;
it needs a JDK):

    python reasoner.py ontology.ttl       the release: no impossible class
    python reasoner.py ontology-v0.ttl    the first draft: two (see explanations/)

Run from ontology/, after data/fetch_data.py (v0 imports Linked GTFS as
published, which it fetches). Needs owlready2==0.51 (pip install owlready2==0.51).
"""

import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from rdflib import OWL, RDFS, XSD, Graph

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "catalog-v001.xml"
TR = "https://ul.edu.lb/kr/transit#"


def catalog_map(catalog=CATALOG):
    """IRI -> local file, read from the Protégé catalog (and the catalogs it names)."""
    ns = {"c": "urn:oasis:names:tc:entity:xmlns:xml:catalog"}
    found, todo, seen = {}, [catalog], set()
    while todo:
        cat = todo.pop()
        if cat in seen or not cat.exists():
            continue
        seen.add(cat)
        root = ET.parse(cat).getroot()
        for u in root.iter("{%s}uri" % ns["c"]):
            found.setdefault(u.get("name"), (cat.parent / u.get("uri")).resolve())
        for n in root.iter("{%s}nextCatalog" % ns["c"]):
            todo.append((cat.parent / n.get("catalog")).resolve())
    return found


def _parse(g, path):
    fmt = "turtle" if path.suffix == ".ttl" else "xml"
    g.parse(path, format=fmt)


def merged_graph(start):
    """One graph holding the start file and everything it imports, with no owl:imports left."""
    cmap = catalog_map()
    g, todo, done = Graph(), [Path(start).resolve()], set()
    while todo:
        path = todo.pop()
        if path in done:
            continue
        done.add(path)
        part = Graph()
        _parse(part, path)
        for _, _, imp in part.triples((None, OWL.imports, None)):
            key = str(imp)
            target = cmap.get(key) or cmap.get(key.rstrip("/#")) or cmap.get(key + "/")
            if target is None:
                raise SystemExit(f"Import not found in the catalog: {key}. Add it to catalog-v001.xml.")
            todo.append(target)
        part.remove((None, OWL.imports, None))
        g += part
    # Linked GTFS gives arrival and departure times the range xsd:duration,
    # a datatype OWL 2 left out, and HermiT stops on it. Protégé's HermiT
    # ignores such datatypes; this does the same, by dropping those ranges.
    for prop in list(g.subjects(RDFS.range, XSD.duration)):
        g.remove((prop, RDFS.range, XSD.duration))
    return g


def reason(start):
    """Load the start file with its imports into owlready2, run HermiT, return the world."""
    import owlready2
    g = merged_graph(start)
    tmp = Path(tempfile.mkdtemp()) / "merged.nt"
    g.serialize(tmp, format="nt", encoding="utf-8")
    world = owlready2.World()
    onto = world.get_ontology(str(tmp)).load()  # a plain path: owlready2 misreads file:///C:/ on Windows
    try:
        with onto:
            owlready2.sync_reasoner_hermit(world, infer_property_values=False, debug=0)
    except owlready2.OwlReadyInconsistentOntologyError:
        world.inconsistent = True
        return world
    world.inconsistent = False
    return world


def label(entity):
    """The English label if there is one, else the IRI's last part."""
    labels = list(entity.label)
    for lab in labels:
        if getattr(lab, "lang", None) in (None, "", "en"):
            return str(lab)
    if labels:
        return str(labels[0])
    return entity.iri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def summary(world):
    """Impossible classes of ours, and the inferred classes of every individual of ours."""
    if world.inconsistent:
        return {"inconsistent": True, "impossible": [], "types": {}}
    impossible = sorted(label(c) for c in world.inconsistent_classes()
                        if c.iri.startswith(TR))
    types = {}
    for ind in world.individuals():
        if "/kr/id/" in ind.iri:
            types[label(ind)] = sorted(label(c) for c in ind.is_a if hasattr(c, "iri"))
    return {"inconsistent": False, "impossible": impossible, "types": types}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    s = summary(reason(sys.argv[1]))
    if s["inconsistent"]:
        print("The ontology is inconsistent: it contradicts itself, so every answer is worthless.")
    print("Impossible classes (equivalent to owl:Nothing):", ", ".join(s["impossible"]) or "none")
    for name, cls in sorted(s["types"].items()):
        print(f"  {name}: {', '.join(cls)}")
