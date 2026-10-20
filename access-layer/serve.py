"""The TEXT2SPARQL contract: one GET address that takes a question and returns
the query the access layer wrote for it.

    python serve.py                                   serves on http://127.0.0.1:8000
    GET /?question=How many night trips are there?&dataset=https://ul.edu.lb/kr/halifax/
    ->  {"dataset": "...", "question": "...", "query": "SELECT ..."}

A refusal comes back as a query that returns nothing, with the reason in a
comment, so a harness still gets valid SPARQL. text2sparql-client can call
this address (see README, optional).
"""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from access_layer import answer, load_examples, open_store

DATASET = "https://ul.edu.lb/kr/halifax/"
STORE, EXAMPLES = open_store(), load_examples()


def query_for(question):
    r = answer(question, STORE, EXAMPLES)
    if r["refused"]:
        reason = r["refused"].replace("\n", " ")
        return f"# {reason}\nSELECT * WHERE {{ FILTER(false) }}"
    return r["query"]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        args = parse_qs(urlparse(self.path).query)
        question, dataset = args.get("question", [""])[0], args.get("dataset", [DATASET])[0]
        if not question or dataset != DATASET:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error": "give ?question=... and dataset=https://ul.edu.lb/kr/halifax/"}')
            return
        body = json.dumps({"dataset": dataset, "question": question, "query": query_for(question)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print("  " + fmt % args)


def main():
    host, port = os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8000"))
    print(f"serving the TEXT2SPARQL contract on http://{host}:{port}/?question=...&dataset={DATASET}")
    HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
