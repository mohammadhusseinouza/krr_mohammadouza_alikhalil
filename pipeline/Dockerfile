# The graph pipeline as a one-shot container: map, SHACL gate, VoID, load.
FROM python:3.12-slim
WORKDIR /work
COPY pipeline/requirements-pipeline.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-pipeline.txt \
 && pip install --no-cache-dir --no-deps morph-kgc==2.10.0
# The repository itself is mounted at /work (docker-compose.yml), so edits to
# the mapping, ontology or shapes need no rebuild.
CMD ["python", "pipeline/run.py"]
