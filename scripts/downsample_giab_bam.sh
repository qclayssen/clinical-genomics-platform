#!/usr/bin/env bash
# Downsample the GIAB HG002 300x chr20 BAM to a representative clinical depth and write
# paired FASTQs for the pipeline (Phase 3 / ADR-0032, VAL-02).
#
# Subsampling is by read-name hash (samtools view -s SEED.FRACTION), so both mates of a
# pair are kept or dropped together, and the same seed reproduces the same read set.
#
#   ./scripts/downsample_giab_bam.sh <bam> <out_prefix> [target_depth] [region]
#
#   ./scripts/downsample_giab_bam.sh HG002.GRCh38.300x_chr20.bam \
#       pipeline/assets/testdata/real/full_chr20/HG002_chr20_35x 35
#   ./scripts/downsample_giab_bam.sh HG002.GRCh38.300x_chr20.bam \
#       pipeline/assets/testdata/real/window/HG002_chr20_window_35x 35 chr20:1000000-2000000
#
# Source (public, CC0): https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/data/
#   AshkenazimTrio/HG002_NA24385_son/NIST_HiSeq_HG002_Homogeneity-10953946/
#   NHGRI_Illumina300X_AJtrio_novoalign_bams/HG002.GRCh38.300x_chr20.bam
set -euo pipefail

BAM="${1:?usage: $0 <bam> <out_prefix> [target_depth] [region]}"
OUT="${2:?usage: $0 <bam> <out_prefix> [target_depth] [region]}"
TARGET="${3:-35}"
REGION="${4:-chr20}"
SEED=42
THREADS="${THREADS:-4}"

mkdir -p "$(dirname "${OUT}")"

# Mean depth of the source over the region, primary non-duplicate reads only —
# the depth the fraction is computed against.
SRC_DEPTH=$(samtools depth -a -r "${REGION}" -G 0xD04 "${BAM}" \
    | awk '{s+=$3; n++} END {printf "%.2f", s/n}')
FRACTION=$(awk -v t="${TARGET}" -v d="${SRC_DEPTH}" 'BEGIN {f=t/d; if (f>=1) f=0.9999; printf "%.4f", f}')
SUBSAMPLE="${SEED}${FRACTION#0}"   # e.g. 42.1368 — samtools seed.fraction syntax

echo "source mean depth ${SRC_DEPTH}x over ${REGION}; fraction ${FRACTION} (seed ${SEED}) → ~${TARGET}x"

samtools view -@ "${THREADS}" -u -F 0x900 -s "${SUBSAMPLE}" "${BAM}" "${REGION}" \
    | samtools collate -@ "${THREADS}" -u -O - "${OUT}.collate" \
    | samtools fastq -@ "${THREADS}" -n -c 6 \
        -1 "${OUT}_R1.fastq.gz" -2 "${OUT}_R2.fastq.gz" \
        -0 /dev/null -s /dev/null

printf 'source_bam\tregion\tsource_mean_depth\ttarget_depth\tseed\tfraction\n%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$(basename "${BAM}")" "${REGION}" "${SRC_DEPTH}" "${TARGET}" "${SEED}" "${FRACTION}" \
    > "${OUT}.downsample.tsv"
echo "wrote ${OUT}_R1.fastq.gz ${OUT}_R2.fastq.gz ${OUT}.downsample.tsv"
