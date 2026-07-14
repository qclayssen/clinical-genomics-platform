"""FAISS-based retriever for RAG context passage retrieval.

Performs cosine similarity search over a pre-built FAISS index of gene/variant
annotations, filtering by a configurable similarity threshold and returning
at most top-k results.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

try:
    import faiss
except ImportError:
    faiss = None  # type: ignore[assignment]


class FAISSRetriever:
    """Retrieve context passages from a FAISS index using cosine similarity.

    The index is expected to be built with ``IndexFlatIP`` over L2-normalized
    vectors, so inner product equals cosine similarity.

    Parameters
    ----------
    index_path : str
        Path to the saved FAISS index file.
    passages : list[dict]
        List of passage metadata dicts, aligned by index position.
        Each dict should contain at minimum: ``text``, ``gene``, ``source``.
    """

    def __init__(self, index_path: str, passages: list[dict]) -> None:
        if faiss is None:
            raise ImportError(
                "faiss-cpu is required for retrieval. "
                "Install it with: pip install faiss-cpu"
            )
        self._index = faiss.read_index(index_path)
        self._passages = passages

    @classmethod
    def from_directory(cls, dir_path: str) -> "FAISSRetriever":
        """Load a FAISSRetriever from a saved index directory.

        Expects the directory to contain:
        - ``index.faiss``: The FAISS index file
        - ``passages.jsonl``: One JSON object per line with passage metadata

        Parameters
        ----------
        dir_path : str
            Path to the directory containing the index and passages files.

        Returns
        -------
        FAISSRetriever
            Initialized retriever ready for queries.
        """
        if faiss is None:
            raise ImportError(
                "faiss-cpu is required for retrieval. "
                "Install it with: pip install faiss-cpu"
            )
        index_path = os.path.join(dir_path, "index.faiss")
        passages_path = os.path.join(dir_path, "passages.jsonl")

        passages: list[dict] = []
        with open(passages_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    passages.append(json.loads(line))

        return cls(index_path=index_path, passages=passages)

    def retrieve(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        threshold: float = 0.70,
    ) -> list[dict]:
        """Search the FAISS index and return filtered results.

        Parameters
        ----------
        query_embedding : np.ndarray
            384-dimensional float32 query vector (should be L2-normalized).
        top_k : int
            Maximum number of results to return. Default: 5.
        threshold : float
            Minimum cosine similarity score for inclusion. Default: 0.70.

        Returns
        -------
        list[dict]
            Results ordered by descending similarity score. Each dict contains:
            - ``text``: The passage text
            - ``score``: Cosine similarity score (float)
            - ``metadata``: Dict with ``gene``, ``source``, and any other fields
        """
        # Ensure query is the right shape for FAISS: (1, dim)
        query = np.asarray(query_embedding, dtype=np.float32)
        if query.ndim == 1:
            query = query.reshape(1, -1)

        # Search for more candidates than top_k to allow filtering
        n_search = min(top_k * 2, self._index.ntotal)
        scores, indices = self._index.search(query, n_search)

        results: list[dict] = []
        for score, idx in zip(scores[0], indices[0]):
            # FAISS returns -1 for indices when fewer results exist
            if idx == -1:
                continue
            # Filter by similarity threshold
            if score < threshold:
                continue
            passage = self._passages[idx]
            results.append(
                {
                    "text": passage["text"],
                    "score": float(score),
                    "metadata": {
                        k: v for k, v in passage.items() if k != "text"
                    },
                }
            )
            if len(results) >= top_k:
                break

        # Sort by descending similarity (should already be sorted from FAISS)
        results.sort(key=lambda r: r["score"], reverse=True)
        return results
