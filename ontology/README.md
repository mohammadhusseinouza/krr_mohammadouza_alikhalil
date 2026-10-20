# ontology/

The Halifax transit ontology (Session 3), as deployed.

| File | What it is |
|---|---|
| `ontology.ttl` | The release, version IRI `https://ul.edu.lb/kr/transit/1.1.0` (prior: 1.0.0, see its header). The pipeline validates the data together with it, and loads it into the endpoint. |
| `linked-gtfs-corrected.ttl` | The published vocabulary we reuse, Linked GTFS (CC BY 3.0), with one fix: four properties had two domains or two ranges, which OWL reads as "both" (every route a fare rule). Each pair is one `owl:unionOf` now; the file's header lists the changes, as the licence requires. `ontology.ttl` imports it. |
| `catalog-v001.xml` | Lets Protégé and `reasoner.py` find the imports offline. The published Linked GTFS is fetched to `data/linked-gtfs/gtfs.ttl` by `data/fetch_data.py`. |
| `competency_questions.md` | The six questions, written before the axioms, and the class that answers each. |
| `reasoner.py`, `reasoner-run.txt` | HermiT, offline; the dated run: no impossible class in the release, two in the draft. |
| `ontology-v0.ttl`, `explanations/` | The first draft, and why each of its two classes was impossible, axiom by axiom (ELK and HermiT). |

**Reuse, not invention.** Every class of ours is a subclass of a Linked
GTFS class (`gtfs:Trip`, `gtfs:Route`, `gtfs:Stop`, `gtfs:CalendarDateRule`)
or is defined with its published values (`gtfs:Bus`, `gtfs:Ferry`). Our
namespace, `https://ul.edu.lb/kr/transit#` (`tr:`), holds only what Linked
GTFS does not say.

**Profile.** OWL 2 DL: 4 classes are EL, 4 need DL (cardinality, and
`xsd:boolean`). Each class says which, in `tr:profile`.

**Run the reasoner** (needs a JDK and `pip install owlready2==0.51`):

```sh
cd ontology
python reasoner.py ontology.ttl       # Impossible classes: none
python reasoner.py ontology-v0.ttl    # Ferry trip, Single-route stop
```

**Alignment outward.** Every class of ours is a subclass of a Linked GTFS
class; beyond it, `tr:FerryTrip skos:closeMatch schema:BoatTrip`
(schema.org: "A trip on a commercial ferry line"). Close, not exact: ours
is one scheduled run in a timetable. No other class of ours has a
counterpart we could check.

**A new version** gets a new version IRI and `owl:priorVersion`. 1.1.0
deleted `tr:CancelledTrip` (it answered no competency question) and added
the alignment; the changes are listed in the file's header.
