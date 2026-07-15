"""RAG (Retrieval-Augmented Generation) module for clinical genomics reporting.

Provides embedding, indexing, and retrieval over ClinVar/ClinGen gene annotations
for chr20 target region genes used in the HG002 variant calling pipeline.
"""

from .embeddings import EmbeddingModel
from .retriever import FAISSRetriever

__all__ = ["EmbeddingModel", "FAISSRetriever"]
