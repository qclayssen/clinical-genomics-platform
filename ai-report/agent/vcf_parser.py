"""VCF parser for variant extraction.

Parses standard VCF files (plain text or gzipped) and extracts variant
records for the interpretation agent. Supports:
- VCFv4.x format
- Gzipped (.vcf.gz) and plain (.vcf) files
- PASS-only filtering
- Gene annotation via chr20 gene coordinate lookup
- Max variant limit to bound agent runtime

Usage:
    python -m ai_report.agent.vcf_parser tests/fixtures/tiny_truth.vcf.gz
"""

from __future__ import annotations

import gzip
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from .data.knowledge_base import KnowledgeBase
from .react import Variant

logger = logging.getLogger(__name__)


def parse_vcf(
    path: str,
    max_variants: int = 50,
    pass_only: bool = True,
    min_qual: float = 0.0,
    genes: Optional[list[str]] = None,
    region: Optional[str] = None,
    kb: Optional[KnowledgeBase] = None,
) -> list[Variant]:
    """Parse a VCF file and extract variant records.

    Parameters
    ----------
    path : str
        Path to VCF file (.vcf or .vcf.gz).
    max_variants : int
        Maximum number of variants to return (bounds agent runtime).
    pass_only : bool
        If True, only include variants with FILTER == PASS.
    min_qual : float
        Minimum QUAL score to include (0.0 = no filter).
    genes : list[str], optional
        If provided, only include variants in these genes.
    region : str, optional
        If provided, only include variants in this region (e.g., 'chr20:1000000-2000000').
    kb : KnowledgeBase, optional
        Knowledge base for position-to-gene mapping. Creates one if needed.

    Returns
    -------
    list[Variant]
        Parsed variant records with gene annotations.

    Raises
    ------
    FileNotFoundError
        If the VCF file doesn't exist.
    ValueError
        If the file is not valid VCF format.
    """
    path_obj = Path(path)
    if not path_obj.exists():
        raise FileNotFoundError(f"VCF file not found: {path}")

    # Parse region filter if provided
    region_chrom, region_start, region_end = None, None, None
    if region:
        region_chrom, coords = _parse_region(region)
        if coords:
            region_start, region_end = coords

    # Set up gene annotation
    _kb = kb or KnowledgeBase()
    try:
        variants: list[Variant] = []

        # Open file (handle gzip vs plain)
        opener = gzip.open if _is_gzipped(path) else open
        mode = "rt" if _is_gzipped(path) else "r"

        with opener(path, mode) as fh:  # type: ignore[call-overload]
            for line in fh:
                line = line.strip()

                # Skip headers
                if line.startswith("#"):
                    if line.startswith("#CHROM"):
                        # Validate VCF header
                        fields = line.split("\t")
                        if len(fields) < 8:
                            raise ValueError(
                                f"Invalid VCF header: expected at least 8 columns, got {len(fields)}"
                            )
                    continue

                if not line:
                    continue

                # Parse variant line
                variant = _parse_vcf_line(line)
                if variant is None:
                    continue

                # Apply filters
                if pass_only and variant.filter_status != "PASS":
                    continue

                if min_qual > 0 and variant.qual < min_qual:
                    continue

                if region_chrom and variant.chrom != region_chrom:
                    continue

                if region_start is not None and variant.pos < region_start:
                    continue

                if region_end is not None and variant.pos > region_end:
                    continue

                # Annotate with gene
                if not variant.gene:
                    gene = _kb.position_to_gene(variant.chrom, variant.pos)
                    if gene:
                        variant.gene = gene

                # Apply gene filter
                if genes and variant.gene not in genes:
                    continue

                variants.append(variant)

                if len(variants) >= max_variants:
                    logger.info(f"Reached max_variants limit ({max_variants})")
                    break

        logger.info(f"Parsed {len(variants)} variants from {path}")
        return variants

    finally:
        if kb is None:
            _kb.close()


def _is_gzipped(path: str) -> bool:
    """Check if a file is gzipped based on extension or magic bytes."""
    if path.endswith(".gz") or path.endswith(".bgz"):
        return True
    # Check magic bytes
    try:
        with open(path, "rb") as f:
            magic = f.read(2)
            return magic == b"\x1f\x8b"
    except (IOError, OSError):
        return False


def _parse_region(region: str) -> tuple[Optional[str], Optional[tuple[int, int]]]:
    """Parse a region string like 'chr20:1000000-2000000'.

    Returns (chrom, (start, end)) or (chrom, None) if no coordinates.
    """
    if ":" in region:
        chrom, coords = region.split(":", 1)
        if "-" in coords:
            parts = coords.split("-")
            return chrom, (int(parts[0]), int(parts[1]))
        return chrom, None
    return region, None


def _parse_vcf_line(line: str) -> Optional[Variant]:
    """Parse a single VCF data line into a Variant.

    VCF columns: CHROM POS ID REF ALT QUAL FILTER INFO [FORMAT SAMPLE...]
    """
    fields = line.split("\t")
    if len(fields) < 8:
        return None

    try:
        chrom = fields[0]
        pos = int(fields[1])
        ref = fields[3]
        alt = fields[4]

        # Handle multi-allelic (take first alt allele)
        if "," in alt:
            alt = alt.split(",")[0]

        # QUAL
        qual = 0.0
        if fields[5] != ".":
            try:
                qual = float(fields[5])
            except ValueError:
                qual = 0.0

        # FILTER
        filter_status = fields[6]

        # Genotype (if FORMAT and SAMPLE columns exist)
        genotype = ""
        if len(fields) >= 10 and fields[8].startswith("GT"):
            format_fields = fields[8].split(":")
            sample_fields = fields[9].split(":")
            gt_idx = format_fields.index("GT") if "GT" in format_fields else 0
            if gt_idx < len(sample_fields):
                genotype = sample_fields[gt_idx]

        return Variant(
            chrom=chrom,
            pos=pos,
            ref=ref,
            alt=alt,
            qual=qual,
            filter_status=filter_status,
            genotype=genotype,
        )

    except (ValueError, IndexError) as e:
        logger.warning(f"Failed to parse VCF line: {e}")
        return None


# ═══ CLI Entry Point ══════════════════════════════════════════════════════════


def main() -> int:
    """CLI: parse a VCF and print extracted variants."""
    import argparse

    parser = argparse.ArgumentParser(description="Parse VCF and extract variants")
    parser.add_argument("vcf", help="Path to VCF file (.vcf or .vcf.gz)")
    parser.add_argument("--max", type=int, default=50, help="Max variants to extract")
    parser.add_argument("--all-filters", action="store_true", help="Include non-PASS variants")
    parser.add_argument("--min-qual", type=float, default=0.0, help="Min QUAL score")
    parser.add_argument("--genes", nargs="+", help="Filter to specific genes")
    parser.add_argument("--region", help="Region filter (e.g., chr20:1000000-2000000)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    variants = parse_vcf(
        path=args.vcf,
        max_variants=args.max,
        pass_only=not args.all_filters,
        min_qual=args.min_qual,
        genes=args.genes,
        region=args.region,
    )

    if args.json:
        import json
        print(json.dumps([v.to_dict() for v in variants], indent=2))
    else:
        print(f"Parsed {len(variants)} variants from {args.vcf}")
        print(f"{'CHROM':<8} {'POS':>10} {'REF':<5} {'ALT':<5} {'QUAL':>6} {'GT':<6} {'GENE':<10}")
        print("-" * 60)
        for v in variants:
            print(f"{v.chrom:<8} {v.pos:>10} {v.ref:<5} {v.alt:<5} {v.qual:>6.0f} {v.genotype:<6} {v.gene:<10}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
