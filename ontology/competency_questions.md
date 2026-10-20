# Competency questions

Written before the axioms (Session 3). Each one is recorded in
`ontology.ttl` as a `tr:answersCQ` annotation on the class or classes that
answer it, so a reader of the ontology can see why each class exists.

| # | Competency question | Answered by | What the Halifax data says |
|---|---|---|---|
| 1 | Which trips run past midnight, and on which routes? | `tr:NightTrip` | 217 night trips, all by bus |
| 2 | Which routes are ferry routes, and which are bus routes? | `tr:FerryRoute`, `tr:BusRoute` | FerD and FerW are the ferry routes |
| 3 | Which trips cross the harbour by ferry, and when do they run? | `tr:FerryTrip` | 412 ferry trips |
| 4 | If route R is cut, which stops lose their only route? | `tr:SingleRouteStop` | 957 of the 2,347 served stops have one route |
| 5 | Where can a rider change from one route to another? | `tr:TransferStop` | 1,390 stops have two or more routes |
| 6 | On a given date, which services are cancelled, and which run in their place? | `tr:ServiceRemoval`, `tr:ServiceAddition` | on 2026-10-12 (Thanksgiving): 2 removed, 2 added |

The counts come from the GTFS tables and from SPARQL over the graph, not
from the reasoner. The ontology says what each class means; a query counts
its members.

**What the reasoner cannot do with them.** Under OWL's open world, it can
never put a stop into `tr:SingleRouteStop` from the data: "exactly one
route" needs to know there is no other route, and OWL never assumes that.
CQ 4 and CQ 5 are therefore answered by SPARQL (and checked by SHACL), not
by classification.

**The property we added.** `tr:servedByRoute` (a stop is served by a route)
answers CQ 4 and CQ 5. We first reused `gtfs:route` on stops because the
name fits; its domain is `gtfs:Trip`, which made every such stop a trip and
`Single-route stop` impossible (`explanations/`).

## Every class answers one

```sparql
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX tr:  <https://ul.edu.lb/kr/transit#>
SELECT ?c WHERE {
  ?c a owl:Class .
  FILTER(isIRI(?c) && STRSTARTS(STR(?c), STR(tr:)))
  FILTER NOT EXISTS { ?c tr:answersCQ ?q }
}
```

returns nothing on release 1.1.0. Release 1.0.0 returned one class,
`tr:CancelledTrip`: a static GTFS feed never says a single trip was
cancelled (it says which services run on which dates, CQ 6), and
cancellations of single trips arrive in GTFS Realtime, which this system
does not use. Under the rule that every class answers a competency
question, it had not earned its place, so 1.1.0 deleted it.
