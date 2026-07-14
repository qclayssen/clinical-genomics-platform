"""Tests for the GA4GH computed-identifier primitives.

Includes the known-answer vector from the VRS spec so we verify spec-correctness,
not just internal consistency.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(module_path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


g = _load(ROOT / "pipeline" / "bin" / "ga4gh_ids.py", "ga4gh_ids")


def test_sha512t24u_known_answer_from_vrs_spec():
    # https://vrs.ga4gh.org — Computed Identifiers worked example
    assert g.sha512t24u(b"ACGT") == "aKF498dAxcJAqme6QYQ7EZ07-fiw8Kw2"


def test_sha512t24u_is_32_chars_unpadded_urlsafe():
    d = g.sha512t24u(b"some genomic bytes")
    assert len(d) == 32
    assert "=" not in d and "+" not in d and "/" not in d  # base64url, unpadded


def test_refget_sequence_id_format_and_normalization():
    sid = g.refget_sequence_id("ACGT")
    assert sid == "ga4gh:SQ.aKF498dAxcJAqme6QYQ7EZ07-fiw8Kw2"
    # normalization: whitespace + case must not change the identity
    assert g.refget_sequence_id("acgt") == sid
    assert g.refget_sequence_id("AC\nGT\n") == sid


def test_vrs_allele_digest_is_deterministic_and_prefixed():
    a = g.vrs_allele_digest("ga4gh:SQ.aKF498dAxcJAqme6QYQ7EZ07-fiw8Kw2", 119, 120, "G")
    b = g.vrs_allele_digest("ga4gh:SQ.aKF498dAxcJAqme6QYQ7EZ07-fiw8Kw2", 119, 120, "G")
    assert a == b and a.startswith("ga4gh:VA.")


def test_iter_fasta_reads_tiny_reference():
    fa = ROOT / "pipeline" / "assets" / "testdata" / "tiny_ref.fa"
    contigs = dict(g.iter_fasta(str(fa)))
    assert "chr20" in contigs and len(contigs["chr20"]) == 600
    # its refget id is stable/reproducible
    assert g.refget_sequence_id(contigs["chr20"]).startswith("ga4gh:SQ.")
