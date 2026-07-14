#!/usr/bin/env python3
"""GA4GH computed identifiers (dependency-free).

Implements the `sha512t24u` digest primitive that both the GA4GH **refget** protocol
and the **Variation Representation Specification (VRS)** use for content-based,
collision-resistant identifiers. Reference: https://vrs.ga4gh.org (Computed Identifiers).

    sha512t24u(data) = base64url( SHA-512(data)[:24] )        # 24 bytes -> 32 chars, no padding

Used here to identify the reference sequence by its *content* (a GA4GH refget
`ga4gh:SQ.<digest>` id) rather than only by a build name like "GRCh38.p14". Content-based
identity strengthens the provenance/traceability story with an interoperable standard id:
two labs with the same sequence get the same id, regardless of file name or source.

CLI:
    ga4gh_ids.py --fasta reference.fa        # -> ga4gh:SQ.<digest> per contig
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import sys


def sha512t24u(data: bytes) -> str:
    """GA4GH truncated-digest primitive: base64url(SHA-512(data)[:24]), unpadded."""
    digest = hashlib.sha512(data).digest()[:24]
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _normalize_sequence(seq: str) -> bytes:
    """VRS/refget normalize sequences to uppercase with no whitespace before hashing."""
    return "".join(seq.split()).upper().encode("ascii")


def refget_sequence_id(seq: str) -> str:
    """GA4GH refget / VRS sequence identifier: ga4gh:SQ.<sha512t24u>."""
    return f"ga4gh:SQ.{sha512t24u(_normalize_sequence(seq))}"


def vrs_allele_digest(sequence_id: str, start: int, end: int, alt: str) -> str:
    """A VRS-style allele identifier (ga4gh:VA.<digest>) over an interbase location + state.

    NOTE: this is a *simplified* rendering for demonstration — a fully spec-compliant VRS
    Allele digest serializes the normalized VRS object (LiteralSequenceExpression +
    SequenceLocation) in the canonical VRS form. It is correct in spirit (content-addressed,
    sha512t24u) but should not be treated as a validated VRS id without the ga4gh.vrs library.
    """
    blob = f"{sequence_id}:{start}:{end}:{alt.upper()}".encode("ascii")
    return f"ga4gh:VA.{sha512t24u(blob)}"


def iter_fasta(path: str):
    """Yield (contig_name, sequence) pairs from a FASTA file."""
    name, chunks = None, []
    with open(path) as fh:
        for line in fh:
            if line.startswith(">"):
                if name is not None:
                    yield name, "".join(chunks)
                name = line[1:].strip().split()[0]
                chunks = []
            else:
                chunks.append(line.strip())
    if name is not None:
        yield name, "".join(chunks)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fasta", required=True, help="reference FASTA to identify")
    args = ap.parse_args()
    for name, seq in iter_fasta(args.fasta):
        print(f"{name}\t{refget_sequence_id(seq)}\t({len(seq)} bp)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
