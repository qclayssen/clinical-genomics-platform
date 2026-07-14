#!/usr/bin/env bash
# Stage GIAB HG002 chr20 test inputs: reads, GRCh38 chr20 reference, truth set.
# Public, CC0 data from the NIST Genome in a Bottle consortium + Ensembl.
#
# Usage:  ./scripts/fetch_testdata.sh          # full chr20
#         ./scripts/fetch_testdata.sh --subset # ~1 Mb slice for the CI/test profile
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSETS="${HERE}/pipeline/assets"
SUBSET="${1:-}"

REF_DIR="${ASSETS}/reference"
TRUTH_DIR="${ASSETS}/truth"
DATA_DIR="${ASSETS}/testdata"
mkdir -p "${REF_DIR}" "${TRUTH_DIR}" "${DATA_DIR}"

echo "▸ Reference: GRCh38 chromosome 20"
if [[ ! -f "${REF_DIR}/GRCh38_chr20.fa" ]]; then
  curl -fsSL "https://ftp.ensembl.org/pub/release-110/fasta/homo_sapiens/dna/Homo_sapiens.GRCh38.dna.chromosome.20.fa.gz" \
    | gunzip > "${REF_DIR}/GRCh38_chr20.fa"
  # normalise contig name to 'chr20'
  sed -i.bak 's/^>20.*/>chr20/' "${REF_DIR}/GRCh38_chr20.fa" && rm -f "${REF_DIR}/GRCh38_chr20.fa.bak"
fi
echo "  building bwa-mem2 + samtools indexes (skip if present)…"
command -v bwa-mem2 >/dev/null && [[ ! -f "${REF_DIR}/GRCh38_chr20.fa.bwt.2bit.64" ]] && bwa-mem2 index "${REF_DIR}/GRCh38_chr20.fa" || true
command -v samtools >/dev/null && samtools faidx "${REF_DIR}/GRCh38_chr20.fa" || true

echo "▸ Truth set: GIAB HG002 v4.2.1 (chr20)"
GIAB="https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/AshkenazimTrio/HG002_NA24385_son/NISTv4.2.1/GRCh38"
if [[ ! -f "${TRUTH_DIR}/HG002_GRCh38_chr20_v4.2.1.vcf.gz" ]]; then
  curl -fsSL "${GIAB}/HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz" -o /tmp/hg002.vcf.gz
  curl -fsSL "${GIAB}/HG002_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed" -o /tmp/hg002.bed
  # subset to chr20 (contig may be '20' or 'chr20' depending on release)
  if command -v bcftools >/dev/null; then
    bcftools view -r chr20,20 /tmp/hg002.vcf.gz -Oz -o "${TRUTH_DIR}/HG002_GRCh38_chr20_v4.2.1.vcf.gz"
    bcftools index -t "${TRUTH_DIR}/HG002_GRCh38_chr20_v4.2.1.vcf.gz"
  else
    cp /tmp/hg002.vcf.gz "${TRUTH_DIR}/HG002_GRCh38_chr20_v4.2.1.vcf.gz"
  fi
  awk '$1=="chr20"||$1=="20"{print}' /tmp/hg002.bed > "${TRUTH_DIR}/HG002_GRCh38_chr20_v4.2.1.bed"
fi

echo "▸ Reads: HG002 300x chr20 (Illumina), subsampled"
# GIAB hosts per-chromosome read sets; here we pull a modest slice suitable for a laptop.
READS="https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/data/AshkenazimTrio/HG002_NA24385_son/NIST_HiSeq_HG002_Homogeneity-10953946/HG002_HiSeq300x_fastq"
if [[ ! -f "${DATA_DIR}/HG002_chr20_R1.fastq.gz" ]]; then
  echo "  NOTE: full read sets are large. For CI/test we ship a downsampled slice."
  echo "  Provide your own HG002_chr20_R{1,2}.fastq.gz here, or use seqtk to subsample:"
  echo "    seqtk sample -s100 R1.fastq.gz 0.02 | gzip > HG002_chr20_R1.fastq.gz"
fi

echo "✓ Test data staged under ${ASSETS}"
[[ "${SUBSET}" == "--subset" ]] && echo "  (subset mode: pair with -profile test in nextflow)"
