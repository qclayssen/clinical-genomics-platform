"""Knowledge base access layer for the variant interpretation agent.

Provides typed query interfaces over the chr20_knowledge.db SQLite database,
with automatic connection management and result dataclasses.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_DATA_DIR = Path(__file__).resolve().parent
_DEFAULT_DB = _DATA_DIR / "chr20_knowledge.db"
_ACMG_CRITERIA_PATH = _DATA_DIR / "acmg_criteria.json"
_GENES_BED_PATH = _DATA_DIR / "chr20_genes.bed"


# ═══ Result Dataclasses ═══════════════════════════════════════════════════════


@dataclass
class ClinVarRecord:
    """A ClinVar variant record."""

    variant_id: str
    gene: str
    chrom: str
    pos: int
    ref: str
    alt: str
    hgvs_c: Optional[str] = None
    hgvs_p: Optional[str] = None
    clinical_significance: str = "Uncertain Significance"
    review_status: Optional[str] = None
    review_stars: int = 0
    conditions: Optional[str] = None
    last_evaluated: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "variant_id": self.variant_id,
            "gene": self.gene,
            "chrom": self.chrom,
            "pos": self.pos,
            "ref": self.ref,
            "alt": self.alt,
            "hgvs_c": self.hgvs_c,
            "hgvs_p": self.hgvs_p,
            "clinical_significance": self.clinical_significance,
            "review_status": self.review_status,
            "review_stars": self.review_stars,
            "conditions": self.conditions,
            "last_evaluated": self.last_evaluated,
        }


@dataclass
class GnomADRecord:
    """A gnomAD allele frequency record."""

    chrom: str
    pos: int
    ref: str
    alt: str
    af_global: float
    af_popmax: Optional[float] = None
    homozygote_count: int = 0
    filter_status: str = "PASS"

    def to_dict(self) -> dict:
        return {
            "chrom": self.chrom,
            "pos": self.pos,
            "ref": self.ref,
            "alt": self.alt,
            "af_global": self.af_global,
            "af_popmax": self.af_popmax,
            "homozygote_count": self.homozygote_count,
            "filter_status": self.filter_status,
        }


@dataclass
class GeneRecord:
    """A gene annotation record."""

    gene_symbol: str
    chrom: str
    start: int
    end: int
    strand: str = "+"
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "gene_symbol": self.gene_symbol,
            "chrom": self.chrom,
            "start": self.start,
            "end": self.end,
            "strand": self.strand,
            "description": self.description,
        }


# ═══ Knowledge Base Class ═════════════════════════════════════════════════════


class KnowledgeBase:
    """Local SQLite-backed knowledge base for chr20 ClinVar + gnomAD data.

    Parameters
    ----------
    db_path : str or Path, optional
        Path to the SQLite database. Defaults to the committed chr20_knowledge.db.
    """

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB
        if not self._db_path.exists():
            raise FileNotFoundError(
                f"Knowledge base not found: {self._db_path}. "
                "Run `python scripts/build_chr20_knowledgebase.py` to create it."
            )
        self._conn: Optional[sqlite3.Connection] = None
        self._gene_index: Optional[list[GeneRecord]] = None
        self._acmg_criteria: Optional[dict] = None

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create a SQLite connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "KnowledgeBase":
        """Support use as a context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close connection on context manager exit."""
        self.close()

    # ─── ClinVar Queries ───────────────────────────────────────────────────

    def query_clinvar(
        self, chrom: str, pos: int, ref: str, alt: str
    ) -> list[ClinVarRecord]:
        """Query ClinVar for a specific variant by position and alleles.

        Parameters
        ----------
        chrom : str
            Chromosome (e.g., 'chr20')
        pos : int
            1-based genomic position
        ref : str
            Reference allele
        alt : str
            Alternate allele

        Returns
        -------
        list[ClinVarRecord]
            Matching ClinVar records (typically 0 or 1).
        """
        conn = self._get_conn()
        cur = conn.execute(
            "SELECT * FROM clinvar WHERE chrom = ? AND pos = ? AND ref = ? AND alt = ?",
            (chrom, pos, ref, alt),
        )
        return [ClinVarRecord(**dict(row)) for row in cur.fetchall()]

    def query_clinvar_by_gene(self, gene: str) -> list[ClinVarRecord]:
        """Query all ClinVar records for a given gene symbol."""
        conn = self._get_conn()
        cur = conn.execute("SELECT * FROM clinvar WHERE gene = ?", (gene,))
        return [ClinVarRecord(**dict(row)) for row in cur.fetchall()]

    # ─── gnomAD Queries ────────────────────────────────────────────────────

    def query_gnomad(
        self, chrom: str, pos: int, ref: str, alt: str
    ) -> Optional[GnomADRecord]:
        """Query gnomAD for allele frequency of a specific variant.

        Parameters
        ----------
        chrom : str
            Chromosome (e.g., 'chr20')
        pos : int
            1-based genomic position
        ref : str
            Reference allele
        alt : str
            Alternate allele

        Returns
        -------
        GnomADRecord or None
            Matching gnomAD record, or None if variant not found (implies AF = 0).
        """
        conn = self._get_conn()
        cur = conn.execute(
            "SELECT * FROM gnomad WHERE chrom = ? AND pos = ? AND ref = ? AND alt = ?",
            (chrom, pos, ref, alt),
        )
        row = cur.fetchone()
        if row:
            return GnomADRecord(**dict(row))
        return None

    # ─── Gene Annotation ──────────────────────────────────────────────────

    def _load_gene_index(self) -> list[GeneRecord]:
        """Load gene coordinates from the BED file."""
        if self._gene_index is not None:
            return self._gene_index

        self._gene_index = []
        if not _GENES_BED_PATH.exists():
            return self._gene_index

        with open(_GENES_BED_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 4:
                    self._gene_index.append(GeneRecord(
                        chrom=parts[0],
                        start=int(parts[1]),
                        end=int(parts[2]),
                        gene_symbol=parts[3],
                        strand=parts[4] if len(parts) > 4 else "+",
                        description=parts[5] if len(parts) > 5 else "",
                    ))
        return self._gene_index

    def position_to_gene(self, chrom: str, pos: int) -> Optional[str]:
        """Map a genomic position to a gene symbol using the BED index.

        Returns the first gene whose interval contains the position,
        or None if not in any annotated gene.
        """
        genes = self._load_gene_index()
        for gene in genes:
            if gene.chrom == chrom and gene.start <= pos <= gene.end:
                return gene.gene_symbol
        return None

    def get_gene_info(self, gene_symbol: str) -> list[GeneRecord]:
        """Get gene annotation records for a given symbol."""
        genes = self._load_gene_index()
        return [g for g in genes if g.gene_symbol == gene_symbol]

    # ─── ACMG Criteria ─────────────────────────────────────────────────────

    def get_acmg_criteria(self) -> dict:
        """Load and return the ACMG criteria definitions."""
        if self._acmg_criteria is not None:
            return self._acmg_criteria

        with open(_ACMG_CRITERIA_PATH) as f:
            self._acmg_criteria = json.load(f)
        return self._acmg_criteria

    # ─── Metadata ──────────────────────────────────────────────────────────

    def get_metadata(self) -> dict[str, str]:
        """Return database metadata as a dict."""
        conn = self._get_conn()
        cur = conn.execute("SELECT key, value FROM metadata")
        return {row["key"]: row["value"] for row in cur.fetchall()}
