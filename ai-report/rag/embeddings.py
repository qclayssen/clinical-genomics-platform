"""Embedding model wrapper for sentence-transformers.

Provides a unified interface for generating text embeddings using
the all-MiniLM-L6-v2 model (384-dimensional, float32 vectors).
"""

from __future__ import annotations

import numpy as np

_SENTENCE_TRANSFORMERS_AVAILABLE = True
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    _SENTENCE_TRANSFORMERS_AVAILABLE = False


class EmbeddingModel:
    """Wrapper around sentence-transformers for generating text embeddings.

    Parameters
    ----------
    model_name : str
        HuggingFace model identifier for the sentence-transformer model.
        Defaults to ``sentence-transformers/all-MiniLM-L6-v2`` (384-dim output).
    """

    EMBEDDING_DIM = 384

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        if not _SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "sentence-transformers is required for embedding generation. "
                "Install it with: pip install sentence-transformers"
            )
        self._model = SentenceTransformer(model_name)
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        """Return the model identifier."""
        return self._model_name

    def embed(self, text: str) -> np.ndarray:
        """Embed a single text string.

        Parameters
        ----------
        text : str
            Input text to embed.

        Returns
        -------
        np.ndarray
            384-dimensional float32 embedding vector (L2-normalized).
        """
        embedding = self._model.encode(text, normalize_embeddings=True)
        return np.asarray(embedding, dtype=np.float32)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Embed a batch of text strings.

        Parameters
        ----------
        texts : list[str]
            List of input texts to embed.

        Returns
        -------
        np.ndarray
            Array of shape (len(texts), 384) with float32 embeddings (L2-normalized).
        """
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return np.asarray(embeddings, dtype=np.float32)
