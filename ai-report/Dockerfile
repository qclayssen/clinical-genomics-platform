# RAG Reporter container — FAISS vector store + sentence-transformers + inference.
#
# Reproducibility note: production builds MUST pin the base by immutable digest
# (ADR-0009). Resolve the current digest and pin it deliberately:
#     docker pull python:3.12-slim
#     docker inspect --format='{{index .RepoDigests 0}}' python:3.12-slim
#     # -> FROM python:3.12-slim@sha256:<real-digest>
# A version tag is used here so the image builds without a stale digest;
# swap in the resolved @sha256 digest at release time.
FROM python:3.12-slim

# ---------- system deps ----------
# libgomp1: required by FAISS for OpenMP parallelism
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---------- Python dependencies (pinned for reproducibility) ----------
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt

# ---------- application code ----------
COPY . .

# ---------- build FAISS index at image build time ----------
# The index is baked into the image so the container starts ready to serve.
RUN python -m rag.build_index \
        --input rag/data/chr20_annotations.jsonl \
        --output-dir rag/index

# ---------- runtime ----------
# Default invocation: RAG-augmented report generation.
# Mount metrics.json at /data/metrics.json and collect output at /output/report.txt.
CMD ["python", "infer.py", "--rag", "--metrics", "/data/metrics.json", "--out", "/output/report.txt"]
