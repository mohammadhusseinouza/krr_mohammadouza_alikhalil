# Technical report: a checked knowledge graph of Halifax Transit

This report documents what was deployed (this repository, `docker compose
up --build`), not what was planned. Every number comes from a file in this repository,
named where it is used. The sections follow the course template.

---

## 1. Problem framing and scope

**The question.** Can a transit timetable become a knowledge graph that is
checked, traceable to its source, and answerable by someone who knows no
SPARQL, and what does each knowledge representation technique add?

**The questions the system answers** are the six competency questions of
the ontology (`ontology/competency_questions.md`), each
measurable on the data:

| CQ | Question | Answer in the data |
|---|---|---|
| 1 | Which trips run past midnight, and on which routes? | 217 night trips, all by bus |
| 2 | Which routes are ferry routes, and which are bus routes? | FerD and FerW are ferries |
| 3 | Which trips cross the harbour by ferry? | 412 ferry trips |
| 4 | If route R is cut, which stops lose their only route? | 957 of 2,347 served stops have one route |
| 5 | Where can a rider change routes? | 1,390 stops have two or more |
| 6 | On a date, which services are cancelled, and which run instead? | Thanksgiving 2026: 2 removed, 2 added |

Through the access layer, a person asks these in English, and the test set
(12 answerable questions, 3 to refuse) measures it.

**Left out, and why.** `shapes.txt` (326,349 map points, about 1.3 million
triples that no question uses). Real-time data (GTFS Realtime: a timetable
is not live). Routing ("fastest way from A to B"): dedicated planners do it
far better than SPARQL. Accessibility: the feed has no information on it.

## 2. Data understanding and constraint discovery

**Source.** Halifax Transit's GTFS feed, Open Government Licence – Halifax,
as a dated snapshot from the Mobility Database (`mdb-734-202608240120`,
24 August 2026) with its SHA-256 in `data/fetch_data.py`. The agency's live
URL changes every few months and can have no fixed checksum; the snapshot
cannot change. 9 tables, about 663,000 rows. One row of `stop_times.txt`, the
central table, means "trip X calls at stop Y at time T, as stop number N".

**The constraint inventory** (`data/constraint_inventory.csv`, recomputed by
`data/rule_checks.py`, `data/runs/rule-checks.txt`), each rule with its count:

| # | Rule | Evidence | Verdict |
|---|---|---|---|
| 1 | Every stop time points to a trip and a stop that exist | 0 of 324,165 break it | holds |
| 2 | Stop numbers run 1, 2, 3 and times never go backwards in a trip | 0 across 9,239 trips | holds |
| 3 | One headsign per route and direction | 157 of 162; 10C, 62, 72, 9B do not | **false in the data**: a pattern with exceptions, kept as a Warning |
| 4 | Vehicles call at stops, never at a station | 0 stop times at the 11 stations | holds |
| 5 | Times are `HH:MM:SS` | 76,774 start with a space (breaks GTFS); 6,847 past 24:00 (follows GTFS) | two findings, opposite verdicts |
| 6 | One stop name, one stop | 133 names shared by 267 stops, 12 to 394 m apart | **false**: names do not identify stops |

OpenRefine proposed 93 merges of stop names once the codes were removed;
all would have been wrong ("A after B" and "B after A" are two stops).

## 3. Ontology

**Reused vocabulary.** Linked GTFS (`http://vocab.gtfs.org/terms#`, CC BY
3.0), pinned to commit `fc12d51` with its SHA-256. It is the published
vocabulary for exactly this format, so other GTFS tools can read our graph.

**Our extension** (`tr:`, `ontology/ontology.ttl`):
every class carries a `tr:answersCQ` annotation naming its competency
question (Section 1). Release 1.0.0 had one class with none,
`tr:CancelledTrip`: a static feed never says a single trip was cancelled
(that is GTFS Realtime), so it had not earned its place, and 1.1.0 deleted
it.

**Alignment outward.** Every class of ours is a subclass of a Linked GTFS
class, and `tr:FerryTrip skos:closeMatch schema:BoatTrip` (schema.org: "A
trip on a commercial ferry line"): close, not exact, because ours is one
scheduled run in a timetable. No other class of ours has a counterpart we
could check.

**The reasoner run** (ELK and HermiT, `ontology/reasoner-run.txt` and
`ontology/explanations/`)
found two unsatisfiable classes:

1. `Ferry trip`: Linked GTFS writes `gtfs:route rdfs:range gtfs:Route,
   gtfs:FareRule`. Two ranges mean "both", so with our disjointness axiom
   every route is impossible. OWL cannot un-import an axiom, so we import a
   **corrected copy** (one `owl:unionOf` per double range, the changes listed
   in the file as CC BY 3.0 requires). It should be reported upstream.
2. `Single-route stop`: our own mistake, `gtfs:route` reused on a stop for
   its name; its domain is Trip. Fixed with `tr:servedByRoute`.

The release is clean under HermiT (`ontology/reasoner-run.txt`). **Profile:**
OWL 2 DL: 4 classes are EL, 4 need DL (`Single-route stop` and `Transfer
stop` count routes; `Service removal` and `Service addition` use
`xsd:boolean`, not an EL datatype). **Version IRI:**
`https://ul.edu.lb/kr/transit/1.1.0`, with `owl:priorVersion` 1.0.0; the
pipeline validates the data with it and loads it into the endpoint.

## 4. Constraint validation with SHACL

**The shapes** (`shapes/shapes.ttl`) come from the six
inventory rules, each shape naming its rule.

**SHACL or OWL, rule by rule:**

| Rule | Where | Why |
|---|---|---|
| A night trip is a trip | OWL `subClassOf` | Meaning: it is inferred, not checked |
| No route is a fare rule, no stop is a station | OWL disjointness | Lets the reasoner find contradictions; costs nothing in the data |
| A stop served by exactly one route | SHACL / SPARQL | Under the open world, OWL can never conclude "exactly one" |
| Times as `HH:MM:SS` text, past 24:00 allowed | SHACL pattern | About the data as written; OWL says nothing about a stray space |
| Stop numbers 1, 2, 3 in a trip | SHACL SPARQL constraint | A rule between rows |
| A vehicle never calls at a station | Both | SHACL reports a Violation; HermiT finds the broken sample inconsistent |

**Triage.** Every rule started as a Violation: 23,208 on the full graph.
Each finding was judged with its evidence (`shapes/triage.md`):

| Finding | Count | Fault | Result |
|---|---:|---|---|
| Times written in days (`P1DT1H10M`) | 13,694 | the conversion's: rdflib rewrites durations | Warning, fixed in Section 5 |
| A trip's shape is not a `gtfs:Shape` | 9,239 | the rule's: shapes.txt is not converted | removed |
| A stop shares its name | 268 | the rule's: rule 6 is false | Info |
| Two headsigns in one direction | 5 | the data's: a pattern, one spelling fault | Warning |
| A service with no weekly rule | 2 | the rule's: GTFS allows it | removed |

After triage: 0 Violations. We did not invent an error to show the gate
working on the full feed.

**The gate.** In the stack, on the whole graph, before the endpoint is
loaded (Section 8). In CI (`.github/workflows/shacl-gate.yml`), on
`data/example.sql`, 7 real trips, with the time-order rule that takes about
14 minutes on the whole graph. **The red run:** the same sample with one bus
calling at the station 10001 fails it, `GATE: FAIL, 1 violations`, and the
endpoint is not loaded (`shapes/runs/red-run-pipeline-sample.txt`, a local
run of the CI command). RED RUN ON GITHUB: to add, with its link, once the
team repository exists.

**Published shapes.** No SHACL for GTFS exists that we could find; Linked
GTFS says a feed is a `dcat:Dataset`, so we ran the EU's DCAT-AP 3.0.0 shapes
unchanged. Session 4's feed failed 3 rules (no title, no description, the
language as text); the mapped feed passes (`shapes/runs/dcat-ap-mapped-feed.txt`).

## 5. Operational data integration

**The mapping** (`mapping/mapping.ttl`, R2RML, 22
triples maps) builds the graph from the database: 2,034,562 triples. Times
are built in SQL as text (`PT25H10M`), so rdflib never rewrites them. Run on
the mapped graph, the gate gives 0 Violations, **5** Warnings (the real
headsigns only) and 268 Info: the 13,694 time Warnings are gone, as the
triage predicted. Compared triple by triple with Session 2's converter, every
data triple matches except the 4 feed metadata triples added on purpose.

**Materialized or virtualized.** Ontop answers the same SPARQL straight from
the database in about 3 seconds. **The deployed system materializes**:

- *freshness*: the feed changes every few months, as a new dated snapshot;
  a rebuild per snapshot is enough, nothing needs live data;
- *latency*: queries on the materialized graph take well under a second;
- *workload*: the gate must validate the whole graph before anyone queries
  it, which needs the graph to exist. Ontop would answer queries on data no
  gate has seen.

The database in the stack is SQLite, built from the feed's files. GTFS
arrives as files, not from a database; PostgreSQL gives the same graph
(compared in Session 5) but adds a container and nothing else.

**Entity resolution.** Our stops against OpenStreetMap's 2,536 Halifax stops
(ODbL, snapshot 2026-10-19). OpenStreetMap's `ref` tag is usually the GTFS
stop code, so it is a real answer key, and the matcher may use only names
(codes removed) and distance. Threshold 6: **precision 0.972, recall 0.959**;
threshold 14: 0.999 and 0.808
(`mapping/er/match-stops-result.txt`).

## 6. Prediction and evaluation honesty

**Node classification: is this trip a night trip?** 217 of 9,239 (2.3%).
Night is a clock fact, so the label is hidden in three places: the class,
the missing `gtfs:Trip` type, and every clock time. With the last stop's
hour, PR-AUC is 0.996; with the first stop's hour, 0.989: both are leaks,
not learning.

| Split | Baseline PR-AUC | GNN | Guessing |
|---|---|---|---|
| Random | 0.102 | 0.045 to 0.094 | 0.023 |
| By route | 0.022 to 0.043 | | 0.023 |

The split by route keeps trips of one route out of both sides. **The GNN
loses to the baseline**, reported as such: with the clock removed, the graph
does not say which trip of a route runs late. A time split needs a second
dated feed.

**Link prediction: which route serves this stop?**

| Model | MRR |
|---|---|
| Popularity | about 0.11 |
| TransE | 0.159 to 0.197 |
| Neighbour count | 0.871 to 0.889 |

Trips and shapes are left out as leaks (with shapes, TransE rises from 0.185
to 0.410 on seed 0). Without the second baseline, TransE would have looked
like a win. Several seeds; the spreads are the ranges above
(`model/results/`).

## 7. Access layer

**Grounding.** The model sees a VoID description of the data (classes,
counts, which property links which class), not the whole Linked GTFS
vocabulary, which lists properties the data never uses; and the three
example queries closest to the question.

**Check and repair.** Every query is parsed, and every term checked against
the VoID; an invented term (`gtfs:routeId`) goes back to the model as a
hint, twice at most, then the layer refuses.

**Refusal.** Wheelchair access (0, "no information", in every row),
ridership (not in GTFS), real-time delays (a timetable is not live).

**The score on the deployed graph** (claude-opus-5-5, 2026-10-20,
TEXT2SPARQL set F1, against the running stack, release 1.1.0,
`report/access-layer-score.txt`; recorded in `access-layer/llm-cache.json`,
so `LLM_MODE=replay` reproduces it without a key):

| Setting | Mean F1 (13 questions) | Refused right | Refused wrongly |
|---|---|---|---|
| Schema only | 0.910 | 3 of 3 | 0 |
| With examples (improvement 1) | 0.949 | 3 of 3 | 0 |
| With repair and the class check (improvement 2) | 0.949 | 3 of 3 | 0 |

**What each part added.** The examples fixed question 7 (route FerD's
stops: 0.67 to 1.00) and raised question 8 (0.50 to 0.67). The check and
repair loop never had to run: no query used a term the graph lacks. It is
a safety net, as in the Session 7 lab (`report/access-layer-score-session2-graph*.txt`:
0.917, 0.944, 0.944 on 12 questions, and 0.949 with the class check on 13,
on Session 2's graph).

**The scorer is not the user.** Questions 8 and 11 stay at 0.67 with right
answers: the 16 stops of Bridge Terminal *with their names*, and route 1
*with its count* (496). Set F1 counts every value returned, so a helpful
extra column costs precision. We kept the benchmark's rule and report the
disagreement.

## 8. Deployment and reproducibility

**The stack** (`docker-compose.yml`): Fuseki, a one-shot pipeline
(`pipeline/run.py`), and the access layer; every port on 127.0.0.1, the key
only in `.env`. `docker compose up --build` from a clean checkout fetches
the feed snapshot and checks its SHA-256, loads it into SQLite, maps it,
gates it, describes it and loads it. The access layer starts only if the
pipeline succeeded, so **the endpoint is only ever loaded with data that
passed the gate**.

**Provenance.** A PROV-O record in its own named graph: the deployed graph
was derived from the eight tables, each with its SHA-256; the run used the
mapping, the ontology, Linked GTFS and the shapes, each with its SHA-256;
the run's start and end, and the gate's result.

**Reproducibility.** Pinned feed snapshot, vocabulary commit, Python
packages and Fuseki release. The gate's PASS is recorded against the
SHA-256 of every input it depends on, so a restart with the same inputs is
up in about 3 minutes instead of 15, and changing one row runs the gate
again.

**The clean-checkout run** (2026-10-20, Docker Desktop on Windows 11,
`pipeline/runs/first-run.txt`): the mapping gave 2,034,562 triples and the
gate 0 Violations, 5 Warnings and 268 Info in 650 s, the same as the labs.
With release 1.1.0 of the ontology, the gate ran again (652.6 s, the same
result), and the endpoint holds 2,035,614 triples (the graph, the ontology,
Linked GTFS). `pipeline/check_stack.py` then passes every layer against the
running stack (`pipeline/runs/check-stack.txt`): the gate, 496 trips on
route 1, the night trip trap (9,022 against 9,239), release 1.1.0, 8 source
files with their SHA-256, and, through the access layer's server, one
question (496) and one refusal (wheelchair accessibility). The model's baseline, rerun on the
deployed `build/graph.nt`, gives exactly the recorded numbers.

**What deploying surfaced:**

- **A VoID that described less than the endpoint holds.** Written from the
  graph alone, it lost the classes Linked GTFS gives its values (`gtfs:Bus`
  is a `gtfs:RouteType` only in the vocabulary). It now describes the graph,
  the ontology and Linked GTFS together.
- **Blank nodes split by a parallel parser.** pyoxigraph's `bulk_load`
  parses N-Triples in parallel chunks, and a blank node whose triples fall
  in two chunks becomes two nodes: the weekly rules' date ranges lost their
  link, and `schema:startDate` disappeared from the VoID (480 triples instead
  of 486). Reading the same file as Turtle fixes it. The course template's
  `make_void.py` loads N-Triples the same way.
- **Replay stops working across graphs.** A recorded answer is found by its
  exact prompt, and the prompt holds the VoID, which describes the deployed
  graph, so the Session 7 recording could not be replayed on it. The score
  was recorded again on the deployed graph (Section 7).
- **Two practical traps:** two stacks cannot share port 3030; and Python
  buffers its output in a container (`PYTHONUNBUFFERED=1`), so the access
  layer looked silent while it served.

## 9. Open problem: reproducible results

**The question.** When a knowledge graph completion method reports a gain,
does the gain survive a fair comparison: a strong baseline, a tuned
competitor, and an evaluation that cannot be won by how ties are ranked?

**Where it appears in our system.** Session 6's link prediction asks which
of 81 routes serves a stop whose link was hidden (5,160 links, 10% hidden,
three seeds). TransE scored MRR 0.159 to 0.197 against 0.104 to 0.116 for
the popularity baseline (`model/results/link-prediction.txt`). Read alone,
that is an MRR 53% to 75% higher, seed by seed: the kind of result the three papers below
warn about. It did not survive our own comparison: a second, simple
baseline, which ranks routes by how many of the stop's neighbouring stops
they serve, scored 0.871 to 0.889.

**What the three sources found.**

- *Kadlec, Bajgar and Kleindienst (2017)* showed that an old model,
  DistMult, carefully tuned, outperformed most of the newer and more complex
  models reported on the standard FB15k benchmark. Part of the progress the
  field reported came from comparing against baselines that had not been
  given the same effort.
- *Ruffinelli, Broscheit and Gemulla (2020)* studied how embeddings are
  trained (the loss, the negative sampling, the regularisation, the
  hyperparameters) in a large, controlled search, and found that the
  training setup can matter as much as the model: older models, trained
  well, become competitive with the newer ones, and the differences between
  models are smaller than the papers proposing them reported.
- *Sun and others (2020)* showed that several recent methods owed much of
  their reported gain to the evaluation protocol: when many candidates get
  the same score, ranking the correct answer first among them inflates the
  result. Under a protocol that places it at random among its ties, those
  gains largely disappear.

**What we did with them.** We tested our own result against each warning.

1. *A strong baseline* (Kadlec and others): the neighbour count was added
   for exactly this reason, and it is the strongest model we have.
2. *The tie protocol* (Sun and others): our ranking keeps tied routes in
   list order, so the true route's place among its ties depended on its
   name. `model/tie_check.py` re-scores both baselines with the true route
   first, last, and at random among its ties
   (`model/results/tie-check.txt`). The neighbour count has a tie on only
   12 to 20 of the 516 hidden links per seed, and its MRR stays between
   0.871 and 0.889 under the most pessimistic protocol. Popularity ties on
   about half of its links, but still moves only between 0.103 and 0.118.
   TransE's scores are floating point numbers and do not tie. The
   comparison holds under every protocol.
3. *Several seeds, and leaks removed*: three splits, with the trips and the
   shapes kept out, because together they *are* the answer (with the shapes
   in, TransE rises from 0.185 to 0.410 on seed 0).

**Our position.** A gain in link prediction is a result only against the
strongest simple model the data allows, under an evaluation that ties
cannot inflate. On a transit network the strongest simple model is the
network itself: routes serve runs of neighbouring stops, so the neighbours
of a stop nearly name its routes. An embedding has to beat that, not
popularity, and on our data TransE falls far short of it. We therefore do
not claim that a graph embedding helps here. More broadly, the course's
method (a baseline built from what the domain already knows) is the same
discipline the three papers ask of the field, and on our data it changed
the conclusion.

**What we could not do, and what it means.** Ruffinelli and others' warning
applies to us: our TransE ran with one setting (32 dimensions, 150 epochs),
untuned. A tuned TransE, or another model, might close part of the gap, so
our result says "this TransE does not beat the structure", not "no
embedding can". And with one feed snapshot we have no time split: a link
hidden at random is easier to recover than a route that is new next season,
which is the case a real predictor would face. A second dated feed would
allow that test.

**References**

1. Rudolf Kadlec, Ondřej Bajgar and Jan Kleindienst. *Knowledge Base
   Completion: Baselines Strike Back.* Proceedings of the 2nd Workshop on
   Representation Learning for NLP (RepL4NLP), ACL, 2017.
2. Daniel Ruffinelli, Samuel Broscheit and Rainer Gemulla. *You CAN Teach an
   Old Dog New Tricks! On Training Knowledge Graph Embeddings.*
   International Conference on Learning Representations (ICLR), 2020.
3. Zhiqing Sun, Shikhar Vashishth, Soumya Sanyal, Partha Talukdar and Yiming
   Yang. *A Re-evaluation of Knowledge Graph Completion Methods.*
   Proceedings of the 58th Annual Meeting of the Association for
   Computational Linguistics (ACL), 2020.

## Licences

| Ontology, vocabulary or dataset | Licence | Where used |
|---|---|---|
| Halifax Transit GTFS feed | Open Government Licence – Halifax (attribution) | the data, all sessions |
| Linked GTFS | CC BY 3.0 | vocabulary; corrected copy in Session 3 |
| OpenStreetMap stops | ODbL | entity resolution, Session 5 |
| DCAT-AP 3.0.0 shapes | CC BY 4.0 | published shapes, Sessions 4 and 5 |
