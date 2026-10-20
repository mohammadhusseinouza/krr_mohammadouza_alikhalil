# access-layer/

Questions in English become SPARQL over the endpoint (Session 7): grounded
in `build/void.ttl` (what the endpoint holds) and the three closest
examples, checked, repaired up to twice, or refused.

**The model:** Claude (`ANTHROPIC_API_KEY` in `.env`, model
`claude-opus-5-5`) or Gemini (`GOOGLE_API_KEY`, `gemini-3.5-flash-lite`),
whichever key `.env` holds; with both, `LLM_PROVIDER=anthropic` or `gemini`
chooses. The prompt, the check, the repair loop and the cache are the same
for both. Claude takes no temperature, so two live runs can differ: a score
names its model and date, and `LLM_MODE=replay` repeats a recorded run.

| File | What it is |
|---|---|
| `access_layer.py` | The five parts: VoID schema, examples, model, check, the loop |
| `prompt_rules.txt` | How things are named in the Halifax graph, and the night trip trap |
| `examples.ttl` | 7 example queries (SHACL vocabulary); none is a test question |
| `questions.yaml` | The test set: 13 answerable, 3 to refuse |
| `make_void.py` | Writes the VoID (the pipeline calls it) |
| `ask.py`, `serve.py` | One question in a terminal; the TEXT2SPARQL contract on port 8000 |
| `check.py`, `broken.sparql` | The check on its own: `gtfs:routeId` is not a property |
| `evaluate.py` | The test set in three settings: schema, examples, repair |

**The check** catches unknown properties and unknown classes; `gtfs:Bus`,
`gtfs:Ferry` and `gtfs:NotAvailable` start with a capital but are values,
not classes (`NAMED_VALUES`).

**The refusals** come from the data, not guesses: wheelchair access (0, "no
information", in every row of the feed), ridership (not in GTFS),
real-time delays (a timetable is not live).

Measure (with the stack up, from this folder):

```sh
SPARQL_ENDPOINT=http://127.0.0.1:3030/kr/sparql python evaluate.py
SPARQL_ENDPOINT=http://127.0.0.1:3030/kr/sparql LLM_MODE=record python evaluate.py > ../report/access-layer-score.txt
```

On Windows PowerShell: `$env:SPARQL_ENDPOINT="http://127.0.0.1:3030/kr/sparql"`,
then `python evaluate.py` (add `$env:LLM_MODE="record"` to record). Commit
`llm-cache.json` with the score; `LLM_MODE=replay` then reproduces it
without the network or a key.
