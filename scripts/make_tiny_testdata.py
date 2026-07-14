#!/usr/bin/env python3
"""Generate tiny placeholder genomic files for the `-profile test -stub` run and CI.

These are NOT real biology — just small, format-valid files so the pipeline's structure
and DAG can be exercised without downloading GIAB data or running heavy tools. For a real
run use scripts/fetch_testdata.sh.

  python3 scripts/make_tiny_testdata.py
"""
import gzip
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "pipeline", "assets", "testdata")
os.makedirs(OUT, exist_ok=True)
rng = random.Random(20260710)


def write(path: str, text: str) -> None:
    with open(path, "w") as fh:
        fh.write(text)
    print("wrote", os.path.relpath(path, HERE))


def write_gz(path: str, text: str) -> None:
    with gzip.open(path, "wt") as fh:
        fh.write(text)
    print("wrote", os.path.relpath(path, HERE))


# ── tiny reference: ~600 bp of 'chr20' ──────────────────────────────────────
ref_seq = "".join(rng.choice("ACGT") for _ in range(600))
fasta = ">chr20\n" + "\n".join(ref_seq[i:i + 60] for i in range(0, len(ref_seq), 60)) + "\n"
write(os.path.join(OUT, "tiny_ref.fa"), fasta)

# ── tiny paired reads derived from the reference (so they'd notionally align) ─
def fastq(read_len: int, n: int) -> str:
    lines = []
    for i in range(n):
        start = rng.randint(0, len(ref_seq) - read_len)
        seq = ref_seq[start:start + read_len]
        lines += [f"@read{i}", seq, "+", "I" * read_len]
    return "\n".join(lines) + "\n"


write_gz(os.path.join(OUT, "HG002_chr20_R1.fastq.gz"), fastq(76, 50))
write_gz(os.path.join(OUT, "HG002_chr20_R2.fastq.gz"), fastq(76, 50))

# ── tiny truth VCF + BED ─────────────────────────────────────────────────────
vcf = (
    "##fileformat=VCFv4.2\n"
    "##contig=<ID=chr20,length=600>\n"
    "##FILTER=<ID=PASS,Description=\"All filters passed\">\n"
    '##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">\n'
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tHG002\n"
    "chr20\t120\t.\tA\tG\t50\tPASS\t.\tGT\t0/1\n"
    "chr20\t300\t.\tC\tT\t50\tPASS\t.\tGT\t1/1\n"
)
write_gz(os.path.join(OUT, "tiny_truth.vcf.gz"), vcf)
write(os.path.join(OUT, "tiny_truth.bed"), "chr20\t0\t600\n")

print("\nTiny test data ready under pipeline/assets/testdata/")
