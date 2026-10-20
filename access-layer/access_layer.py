"""The access layer: a question in English becomes a SPARQL query (Session 7).

Five small parts, each a function you can read on its own:

  schema_text     what the graph holds, read from its VoID description
  pick_examples   the 3 example queries whose questions share most words
  ask_model       one call to the language model (live, recorded or replayed)
  check_query     is the query valid SPARQL, and does it use only real terms?
  answer          the whole loop: ask, check, repair up to 2 times, or refuse

The model is Claude (ANTHROPIC_API_KEY in .env) or Gemini
(GOOGLE_API_KEY), whichever key is there; LLM_PROVIDER=anthropic or gemini
chooses when both are, and LLM_MODEL picks the model. LLM_MODE=replay reads a
recorded run instead (llm-cache.json, written by evaluate.py with
LLM_MODE=record): the fallback when a key does not work.

Compared with the course template: the Halifax graph uses six vocabularies,
not one namespace (gtfs:, tr:, dct:, foaf:, geo:, schema:), so the prefixes,
the check and the VoID description cover all six; and the model is Claude or
Gemini, whichever key .env holds.
"""

import hashlib
import json
import os
import re
import time
from pathlib import Path

import pyoxigraph as ox
import requests
from dotenv import load_dotenv
from rdflib import RDF, Graph, Namespace, URIRef
from rdflib.plugins.sparql import prepareQuery

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
load_dotenv(ROOT / ".env")
GRAPH = ROOT / "build" / "graph.nt"
# The VoID the pipeline wrote for the graph it loaded (the stack sets VOID_FILE).
VOID_FILE = Path(os.environ.get("VOID_FILE", ROOT / "build" / "void.ttl"))
EXAMPLES = HERE / "examples.ttl"
CACHE = HERE / "llm-cache.json"
DATASET = URIRef("https://ul.edu.lb/kr/halifax/void")
GTFS = "http://vocab.gtfs.org/terms#"
VOID = Namespace("http://rdfs.org/ns/void#")
VEXT = Namespace("http://ldf.fi/void-ext#")
SH = Namespace("http://www.w3.org/ns/shacl#")
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai"  # Gemini's OpenAI style address

# The vocabularies the graph's data uses (Session 2's convert_to_rdf.py). The
# check looks at terms of these six; rdf:, rdfs: and xsd: are SPARQL's own.
VOCABS = {"gtfs": GTFS, "tr": "https://ul.edu.lb/kr/transit#", "dct": "http://purl.org/dc/terms/",
          "foaf": "http://xmlns.com/foaf/0.1/", "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
          "schema": "http://schema.org/"}
PREFIXES = dict(VOCABS, rdfs="http://www.w3.org/2000/01/rdf-schema#",
                xsd="http://www.w3.org/2001/XMLSchema#")
# The Linked GTFS individuals the data points at (gtfs:routeType, gtfs:pickupType).
# They start with a capital, like classes, but they are values, not classes.
NAMED_VALUES = {GTFS + "Bus", GTFS + "Ferry", GTFS + "NotAvailable"}


# ---------------------------------------------------------------- the graph
def open_store(path=GRAPH):
    """The graph to ask. With SPARQL_ENDPOINT set (for example
    http://127.0.0.1:3030/kr/sparql, your Session 2 Fuseki), that address;
    otherwise build/graph.nt, the pipeline's graph, loaded in memory (about 3 s)."""
    endpoint = os.environ.get("SPARQL_ENDPOINT")
    if endpoint:
        return endpoint
    store = ox.Store()
    # As Turtle, even an .nt file (N-Triples is a subset): bulk_load parses N-Triples
    # in parallel chunks, and a blank node split across two chunks becomes two nodes.
    store.bulk_load(path=str(path), format=ox.RdfFormat.TURTLE)
    return store


def with_prefixes(query):
    """The query with a PREFIX line for every prefix it uses but does not declare."""
    declared = {m.lower() for m in re.findall(r"PREFIX\s+(\w*):", query, re.I)}
    missing = [f"PREFIX {p}: <{ns}>" for p, ns in PREFIXES.items() if p not in declared]
    return "\n".join(missing + [query]) if missing else query


def run(store, query):
    """Run a SELECT or ASK query; returns a list of rows (dicts of strings) or True/False."""
    if isinstance(store, str):  # a SPARQL endpoint over HTTP
        r = requests.post(store, data={"query": with_prefixes(query)}, timeout=60,
                          headers={"Accept": "application/sparql-results+json"})
        r.raise_for_status()
        res = r.json()
        if "boolean" in res:
            return res["boolean"]
        return [{k: v["value"] for k, v in b.items()} for b in res["results"]["bindings"]]
    res = store.query(with_prefixes(query))
    if isinstance(res, bool):
        return res
    names = [v.value for v in res.variables]
    return [{n: row[n].value for n in names if row[n] is not None} for row in res]


# ---------------------------------------------------------------- schema, from VoID
def load_void(path=VOID_FILE):
    """{class: number of things}, and {property: {class: [target classes or datatypes]}}.
    A property used only on things with no class (a date range's schema:startDate)
    is listed with no class: {property: {}}."""
    g = Graph().parse(path)
    classes, props = {}, {}
    for part in g.objects(DATASET, VOID.classPartition):
        c = str(g.value(part, VOID["class"]))
        classes[c] = int(g.value(part, VOID.entities))
        for pp in g.objects(part, VOID.propertyPartition):
            targets = [str(g.value(o, VOID["class"])) for o in g.objects(pp, VOID.classPartition)]
            targets += [str(g.value(o, VEXT.datatype)) for o in g.objects(pp, VEXT.datatypePartition)]
            props.setdefault(str(g.value(pp, VOID.property)), {})[c] = targets
    for pp in g.objects(DATASET, VOID.propertyPartition):
        props.setdefault(str(g.value(pp, VOID.property)), {})
    return classes, props


def short(iri):
    for p, ns in PREFIXES.items():
        if iri.startswith(ns):
            return f"{p}:{iri[len(ns):]}"
    return f"<{iri}>"


def schema_text(path=VOID_FILE):
    """The schema in a few lines of plain text, for the prompt."""
    classes, props = load_void(path)
    lines = [f"{short(c)} ({n:,} things)" for c, n in sorted(classes.items(), key=lambda x: (-x[1], x[0]))]
    for p, by_class in sorted(props.items(), key=lambda x: short(x[0])):
        for c, targets in sorted(by_class.items()):
            target = " or ".join(sorted(short(t) for t in targets)) or "a thing with no class"
            lines.append(f"{short(c)} {short(p)} {target}")
    loose = sorted(short(p) for p, by_class in props.items() if not by_class)
    if loose:
        lines.append(f"On nodes with no class: {', '.join(loose)}")
    return "\n".join(lines)


# ---------------------------------------------------------------- example queries
def load_examples(path=EXAMPLES):
    """Examples in the SHACL vocabulary: rdfs:comment holds the question, sh:select the query."""
    g = Graph().parse(path)
    out = [{"id": str(ex).rsplit("/", 1)[-1], "question": str(g.value(ex, RDFS.comment)),
            "query": str(g.value(ex, SH.select))}
           for ex in g.subjects(RDF.type, SH.SPARQLExecutable)]
    return sorted(out, key=lambda e: e["id"])


STOP = {"the", "a", "an", "of", "is", "are", "which", "what", "how", "many", "does", "do", "did",
        "in", "by", "to", "there", "with", "their", "each", "and", "on", "at"}


def words(text):
    return set(re.findall(r"[a-z0-9_.]+", text.lower())) - STOP


def pick_examples(question, examples, k=3):
    """The k examples whose questions share the most words with this one (ties: file order)."""
    q = words(question)
    return sorted(examples, key=lambda e: -len(q & words(e["question"])))[:k]


# ---------------------------------------------------------------- the prompt and the model
# How things are named in the Halifax graph, and the night trip trap: prompt_rules.txt.
RULES = (HERE / "prompt_rules.txt").read_text(encoding="utf-8").strip()
RULES_ID = hashlib.sha256(RULES.encode()).hexdigest()[:8]  # recorded outputs name the rules they were made with


def build_prompt(question, schema, examples, hints=None):
    parts = [RULES, "", "Schema (the classes, then: class property target):", schema, ""]
    if examples:
        parts.append("Examples:")
        for e in examples:
            parts += [f"Question: {e['question']}", e["query"].strip(), ""]
    if hints:
        parts += ["Your previous query had these problems. Write it again without them:"]
        parts += [f"- {h}" for h in hints] + [""]
    parts.append(f"Question: {question}")
    return "\n".join(parts)


def provider():
    """anthropic or gemini: LLM_PROVIDER if set, otherwise the one whose key is in .env."""
    chosen = os.environ.get("LLM_PROVIDER")
    if chosen:
        return chosen.lower()
    return "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "gemini"


def model_name():
    default = "claude-opus-5-5" if provider() == "anthropic" else "gemini-3.5-flash-lite"
    return os.environ.get("LLM_MODEL", default)


def prompt_key(prompt):
    return hashlib.sha256(f"{model_name()}\n{prompt}".encode()).hexdigest()[:16]


def ask_model(prompt, mode=None):
    """One call. LLM_MODE live (default): ask the model. record: ask and save the answer.
    replay: return the saved answer for exactly this prompt and model."""
    mode = mode or os.environ.get("LLM_MODE", "live")
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    key = prompt_key(prompt)
    if mode == "replay":
        if key not in cache:
            raise SystemExit(f"No recorded answer for this prompt (key {key}). Replay works only for the "
                             "test set's questions, unchanged, after evaluate.py ran with LLM_MODE=record; "
                             "run live for anything else.")
        return cache[key]["reply"]
    reply = ask_claude(prompt) if provider() == "anthropic" else ask_gemini(prompt)
    if mode == "record":
        cache[key] = {"model": model_name(), "reply": reply}
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")
    return reply


def ask_claude(prompt):
    """One call to Claude, through the Anthropic SDK. Claude Opus 5.5 takes no
    temperature, so two runs can write different queries: replay is what makes
    a run repeatable. fallbacks="default": if a safety check declines the
    request, the API answers it with another Claude model instead."""
    import anthropic  # only needed for this provider

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("No key: put ANTHROPIC_API_KEY in .env (see .env.example), "
                         "or run with LLM_MODE=replay.")
    client = anthropic.Anthropic(max_retries=4)  # the SDK waits and retries on 429 and 5xx itself
    try:
        r = client.beta.messages.create(
            model=model_name(), max_tokens=16000,
            output_config={"effort": os.environ.get("LLM_EFFORT", "medium")},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            messages=[{"role": "user", "content": prompt}])
    except anthropic.RateLimitError:
        raise SystemExit("Still too many requests after four retries. Wait a minute, or run with LLM_MODE=replay.")
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
        raise SystemExit(f"The key was refused ({e.status_code}). Check ANTHROPIC_API_KEY in .env, "
                         "or run with LLM_MODE=replay.")
    except anthropic.BadRequestError as e:
        raise SystemExit(f"The request was refused (400): {str(e)[:200]}")
    except anthropic.APIConnectionError:
        raise SystemExit("Cannot reach the Anthropic API. Check the connection, or run with LLM_MODE=replay.")
    if r.stop_reason == "refusal":  # declined, fallback included: no query to run
        category = r.stop_details.category if r.stop_details else None
        return f"REFUSE: the model declined the request ({category or 'no category'})"
    return "".join(b.text for b in r.content if b.type == "text")


def ask_gemini(prompt):
    """One call to Gemini, through its OpenAI style address (the demo's model)."""
    base = GEMINI
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit("No key: put ANTHROPIC_API_KEY or GOOGLE_API_KEY in .env (see .env.example), "
                         "or run with LLM_MODE=replay.")
    # A free tier limits requests per minute, tokens per minute and requests per
    # day, per project. Wait between calls (4 s keeps under 15 a minute), and
    # on "too many requests" (429) wait longer and try again.
    time.sleep(float(os.environ.get("LLM_DELAY", "4")))
    for attempt in range(4):
        try:
            r = requests.post(f"{base}/chat/completions", timeout=90,
                              headers={"Authorization": f"Bearer {api_key}"},
                              json={"model": model_name(), "temperature": 0,
                                    "messages": [{"role": "user", "content": prompt}]})
        except requests.ConnectionError:
            raise SystemExit(f"Cannot reach the model at {base}. Check the connection, or run with LLM_MODE=replay.")
        if r.status_code != 429:
            break
        if "PerDay" in r.text or "per day" in r.text.lower():
            raise SystemExit("The free tier's daily limit is used up for this project (it resets at midnight "
                             "Pacific time, 10:00 in Beirut). Run with LLM_MODE=replay, or use another "
                             "Gemini model (LLM_MODEL).")
        wait = 20 * (attempt + 1)
        print(f"  (too many requests a minute: waiting {wait} s, then trying again)", flush=True)
        time.sleep(wait)
    if r.status_code == 429:
        raise SystemExit("Still too many requests after four tries. Wait a minute, set LLM_DELAY=8, "
                         "or run with LLM_MODE=replay.")
    if r.status_code in (400, 401, 403):
        raise SystemExit(f"The model refused the key or the request ({r.status_code}): {r.text[:200]}\n"
                         "Check GOOGLE_API_KEY in .env, or run with LLM_MODE=replay.")
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def clean(reply):
    """The query inside a reply, without Markdown fences."""
    m = re.search(r"```(?:sparql|SPARQL)?\s*(.*?)```", reply, re.S)
    return (m.group(1) if m else reply).strip()


# ---------------------------------------------------------------- the check
def vocab_terms(query):
    """Full IRIs of every term of the six vocabularies the query uses, prefixed or written in full."""
    used = set()
    for p, ns in VOCABS.items():
        used |= {ns + t for t in re.findall(rf"(?<![\w:]){p}:([A-Za-z_]\w*)", query)}
        used |= {ns + t for t in re.findall(rf"<{re.escape(ns)}(\w+)>", query)}
    return used


def local(iri):
    return re.split(r"[#/]", iri)[-1]


def unknown_properties(query, classes, props):
    """Problems: properties the query uses that the graph does not have."""
    known = set(props)
    used = {t for t in vocab_terms(query) if local(t)[0].islower()}
    listed = ", ".join(sorted(short(k) for k in known))
    return [f"{short(t)} is not a property of this graph. The properties are: {listed}" for t in sorted(used - known)]


def unknown_classes(query, classes, props):
    """Problems: classes the query uses that the graph does not have. gtfs:Bus,
    gtfs:Ferry and gtfs:NotAvailable start with a capital but are values (NAMED_VALUES)."""
    known = set(classes) | NAMED_VALUES
    used = {t for t in vocab_terms(query) if local(t)[0].isupper()}
    listed = ", ".join(sorted(short(k) for k in classes))
    return [f"{short(t)} is not a class of this graph. The classes are: {listed}" for t in sorted(used - known)]


# The class check is the Session 7 Part B improvement: with it, mean F1 0.949 on 13 questions.
CHECKS = [unknown_properties, unknown_classes]


def check_query(query, void_path=VOID_FILE, checks=None):
    """A list of problems in plain English; an empty list means the query may be run."""
    try:
        prepareQuery(with_prefixes(query))
    except Exception as e:
        return [f"not valid SPARQL: {str(e).splitlines()[0][:150]}"]
    classes, props = load_void(void_path)
    return [p for check in (checks or CHECKS) for p in check(query, classes, props)]


# ---------------------------------------------------------------- the loop
def answer(question, store, examples, use_examples=True, repair=True, checks=None, mode=None, tries=3):
    """Returns {query, rows, refused, attempts}. attempts lists each query tried and its problems.
    repair=False: one try, run as written, no check (what a model alone gives you)."""
    schema = schema_text()
    shots = pick_examples(question, examples) if use_examples else []
    hints, attempts = None, []
    for _ in range(tries if repair else 1):
        reply = ask_model(build_prompt(question, schema, shots, hints), mode)
        if reply.strip().upper().startswith("REFUSE"):
            return {"query": None, "rows": None, "refused": reply.strip(), "attempts": attempts}
        query = clean(reply)
        problems = check_query(query, checks=checks) if repair else []
        if not problems:
            try:
                rows = run(store, query)
                attempts.append({"query": query, "problems": []})
                return {"query": with_prefixes(query), "rows": rows, "refused": None, "attempts": attempts}
            except Exception as e:
                problems = [f"the endpoint rejected it: {str(e).splitlines()[0][:150]}"]
        attempts.append({"query": query, "problems": problems})
        hints = problems
    if not repair:  # no check and no repair: the broken query is the answer, and it answers nothing
        return {"query": with_prefixes(attempts[-1]["query"]), "rows": None, "refused": None, "attempts": attempts}
    return {"query": None, "rows": None, "attempts": attempts,
            "refused": f"REFUSE: no valid query after {len(attempts)} tries"}
