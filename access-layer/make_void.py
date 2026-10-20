"""Describe the Halifax graph with VoID: which classes it has, how many of each,
and which properties link each class to which class or datatype. The same
layout as SIB's void-generator (which needs Java 17 and a SPARQL endpoint).

    python make_void.py GRAPH OUT [MORE...]   describes GRAPH plus MORE, writes OUT

pipeline/run.py calls write_void() with the graph and everything the endpoint
holds beside it (the ontology, Linked GTFS): without Linked GTFS, gtfs:Bus has
no class and the description loses gtfs:RouteType (found on the first deployed
run). Only the data is described (things under https://ul.edu.lb/kr/id/), not
the vocabularies' own classes; and the dataset also lists every property it uses, because two
(schema:startDate, schema:endDate) sit on date ranges that have no class.
"""
import sys
import time
from pathlib import Path

import pyoxigraph as ox

from access_layer import PREFIXES

QUERY = """
PREFIX void: <http://rdfs.org/ns/void#>
PREFIX void-ext: <http://ldf.fi/void-ext#>
CONSTRUCT {
  <https://ul.edu.lb/kr/halifax/void> void:classPartition ?cp ; void:propertyPartition ?dpp .
  ?cp void:class ?c ; void:entities ?n ; void:propertyPartition ?pp .
  ?pp void:property ?p ; void:triples ?t ; void:classPartition ?op ; void-ext:datatypePartition ?dp .
  ?op void:class ?oc .
  ?dp void-ext:datatype ?dt .
  ?dpp void:property ?p2 ; void:triples ?t2 .
} WHERE {
  {
    { SELECT ?c (COUNT(DISTINCT ?s) AS ?n) WHERE {
        ?s a ?c FILTER (STRSTARTS(STR(?s), "https://ul.edu.lb/kr/id/")) } GROUP BY ?c }
    BIND (IRI(CONCAT("https://ul.edu.lb/kr/halifax/void/", REPLACE(STR(?c), "^.*[#/]", ""))) AS ?cp)
    OPTIONAL {
      { SELECT ?c ?p (COUNT(*) AS ?t) (SAMPLE(DATATYPE(?o)) AS ?dt0) WHERE {
          ?s a ?c ; ?p ?o . FILTER (?p != <http://www.w3.org/1999/02/22-rdf-syntax-ns#type>)
          FILTER (STRSTARTS(STR(?s), "https://ul.edu.lb/kr/id/")) } GROUP BY ?c ?p }
      # Every class the values have, not one sample: a service's gtfs:serviceRule
      # points at weekly rules and at date rules.
      OPTIONAL { SELECT DISTINCT ?c ?p ?oc WHERE {
          ?s a ?c ; ?p ?o . ?o a ?oc .
          FILTER (STRSTARTS(STR(?s), "https://ul.edu.lb/kr/id/")) } }
      BIND (IRI(CONCAT("https://ul.edu.lb/kr/halifax/void/", REPLACE(STR(?c), "^.*[#/]", ""), "-",
                       REPLACE(STR(?p), "^.*[#/]", ""))) AS ?pp)
      BIND (IF(BOUND(?oc), IRI(CONCAT(STR(?pp), "-class-", REPLACE(STR(?oc), "^.*[#/]", ""))), ?unbound) AS ?op)
      BIND (IF(BOUND(?dt0) && !BOUND(?oc), ?dt0, ?unbound) AS ?dt)
      BIND (IF(BOUND(?dt), IRI(CONCAT(STR(?pp), "-datatype")), ?unbound) AS ?dp)
    }
  }
  UNION
  {
    # Every property the data uses, also on nodes with no class (a date range).
    { SELECT ?p2 (COUNT(*) AS ?t2) WHERE {
        { ?s ?p2 ?o . FILTER (STRSTARTS(STR(?s), "https://ul.edu.lb/kr/id/")) }
        UNION
        { ?x ?q ?s . ?s ?p2 ?o . FILTER (ISBLANK(?s) && STRSTARTS(STR(?x), "https://ul.edu.lb/kr/id/")) }
        FILTER (?p2 != <http://www.w3.org/1999/02/22-rdf-syntax-ns#type>)
      } GROUP BY ?p2 }
    BIND (IRI(CONCAT("https://ul.edu.lb/kr/halifax/void/property-", REPLACE(STR(?p2), "^.*[#/]", ""))) AS ?dpp)
  }
}
"""


def write_void(graph_path, out_path, extras=()):
    """The VoID of graph_path plus extras (Turtle files), written to out_path.
    Returns the number of VoID triples."""
    store = ox.Store()
    # Every file as Turtle, even graph.nt (N-Triples is a subset of Turtle):
    # bulk_load parses N-Triples in parallel chunks, and a blank node whose
    # triples fall in two chunks becomes two nodes. The date ranges of the
    # weekly rules are blank nodes, and schema:startDate disappeared from the
    # VoID that way (found on the first full run of this repository).
    for path in [graph_path, *extras]:
        store.bulk_load(path=str(path), format=ox.RdfFormat.TURTLE)
    triples = list(store.query(QUERY))
    Path(out_path).write_bytes(ox.serialize(triples, format=ox.RdfFormat.TURTLE,
                                            prefixes=dict(PREFIXES, void="http://rdfs.org/ns/void#",
                                                          **{"void-ext": "http://ldf.fi/void-ext#"})))
    return len(triples)


if __name__ == "__main__":
    t0 = time.time()
    n = write_void(sys.argv[1], sys.argv[2], sys.argv[3:])
    print(f"wrote {Path(sys.argv[2]).name}: {n} VoID triples in {time.time() - t0:.1f} s")
