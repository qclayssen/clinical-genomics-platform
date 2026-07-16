#!/usr/bin/env python3
"""Build a FAISS index from chr20 gene annotation data.

Reads a JSONL file of ClinVar/ClinGen annotations, embeds each entry using
sentence-transformers (all-MiniLM-L6-v2), and saves the FAISS index plus
passage metadata to disk for use by the RAG retriever.

Usage:
    python -m ai_report.rag.build_index [--input DATA_JSONL] [--output-dir DIR]

Or run directly:
    python ai-report/rag/build_index.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np


def load_annotations(input_path: str) -> list[dict]:
    """Load annotation entries from a JSONL file."""
    entries: list[dict] = []
    with open(input_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def build_faiss_index(embeddings: np.ndarray) -> "faiss.IndexFlatIP":
    """Build a FAISS IndexFlatIP from L2-normalized embeddings.

    Using IndexFlatIP (inner product) with normalized vectors gives
    cosine similarity scores directly.
    """
    import faiss

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    return index


def save_index(index: "faiss.IndexFlatIP", passages: list[dict], output_dir: str) -> None:
    """Save the FAISS index and passages metadata to disk."""
    import faiss

    os.makedirs(output_dir, exist_ok=True)
    index_path = os.path.join(output_dir, "index.faiss")
    passages_path = os.path.join(output_dir, "passages.jsonl")

    faiss.write_index(index, index_path)

    with open(passages_path, "w") as f:
        for passage in passages:
            f.write(json.dumps(passage) + "\n")

    print(f"Saved FAISS index ({index.ntotal} vectors) to: {index_path}")
    print(f"Saved passages metadata to: {passages_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build FAISS index from chr20 gene annotations"
    )
    parser.add_argument(
        "--input",
        default=os.path.join(
            os.path.dirname(__file__), "data", "chr20_annotations.jsonl"
        ),
        help="Path to input JSONL file with gene annotations",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(__file__), "index"),
        help="Directory to save the FAISS index and passages",
    )
    args = parser.parse_args()

    # Load annotations
    print(f"Loading annotations from: {args.input}")
    entries = load_annotations(args.input)
    print(f"Loaded {len(entries)} annotation entries")

    if not entries:
        print("ERROR: No annotation entries found.", file=sys.stderr)
        return 1

    # Initialize embedding model
    from .embeddings import EmbeddingModel

    print("Loading embedding model (all-MiniLM-L6-v2)...")
    model = EmbeddingModel()

    # Embed all annotation texts
    texts = [entry["text"] for entry in entries]
    print(f"Embedding {len(texts)} passages...")
    embeddings = model.embed_batch(texts)

    # Normalize vectors for cosine similarity via inner product
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1  # avoid division by zero
    embeddings = embeddings / norms

    # Build and save index
    print("Building FAISS index (IndexFlatIP)...")
    index = build_faiss_index(embeddings)
    save_index(index, entries, args.output_dir)

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
