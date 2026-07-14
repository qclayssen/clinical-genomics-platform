#!/usr/bin/env bash
# Preflight check before a real pipeline run. Verifies tools, then — if data is staged —
# checks that reference / truth VCF / truth BED use CONSISTENT contig names. A contig-name
# mismatch (e.g. '20' vs 'chr20') is the #1 cause of a silently-wrong hap.py result.
#
#   ./scripts/preflight.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSETS="${HERE}/pipeline/assets"
warn=0; fail=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
note() { printf '  \033[33m!\033[0m %s\n' "$1"; warn=$((warn+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }

echo "▸ Tools"
if java -version >/dev/null 2>&1; then ok "java: $(java -version 2>&1 | head -1)"; else bad "working java not found (brew install temurin; the macOS /usr/bin/java stub doesn't count)"; fi
if command -v nextflow >/dev/null; then ok "nextflow: $(nextflow -version 2>&1 | grep -i version | head -1 | tr -s ' ')"; else bad "nextflow not found (brew install nextflow)"; fi
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then ok "docker: running"; else bad "docker not running (start Docker Desktop; 'docker info' must succeed)"; fi

echo "▸ Data staged?"
REF="${ASSETS}/reference/GRCh38_chr20.fa"
TVCF="${ASSETS}/truth/HG002_GRCh38_chr20_v4.2.1.vcf.gz"
TBED="${ASSETS}/truth/HG002_GRCh38_chr20_v4.2.1.bed"
R1="${ASSETS}/testdata/HG002_chr20_R1.fastq.gz"

staged=1
for f in "$REF" "$TVCF" "$TBED"; do
  if [ -s "$f" ]; then ok "present: ${f#$HERE/}"; else note "missing: ${f#$HERE/} (run ./scripts/fetch_testdata.sh)"; staged=0; fi
done
if [ -s "$R1" ]; then
  r1_bytes=$(wc -c < "$R1" | tr -d ' ')
  if [ "$r1_bytes" -lt 10240 ]; then
    note "reads look like the tiny STUB placeholder (${r1_bytes} bytes) — fine for -stub, but replace with real HG002 chr20 FASTQs for measured numbers"
  else
    ok "reads present: ${R1#$HERE/} (${r1_bytes} bytes)"
  fi
else
  note "reads missing: provide real HG002 chr20 FASTQs"
fi

# ── Contig-name consistency (only if reference + truth are staged) ───────────
if [ "$staged" = "1" ]; then
  echo "▸ Contig-name consistency (reference vs truth VCF vs truth BED)"
  ref_contigs=$(grep '^>' "$REF" 2>/dev/null | sed 's/^>//' | awk '{print $1}' | sort -u | tr '\n' ' ')
  if command -v bcftools >/dev/null; then
    vcf_contigs=$(bcftools view -h "$TVCF" 2>/dev/null | grep -oE '##contig=<ID=[^,>]+' | sed 's/.*ID=//' | sort -u | tr '\n' ' ')
    [ -z "$vcf_contigs" ] && vcf_contigs=$(bcftools view "$TVCF" 2>/dev/null | grep -v '^#' | cut -f1 | sort -u | tr '\n' ' ')
  else
    vcf_contigs=$(gzip -dc "$TVCF" 2>/dev/null | grep -v '^#' | cut -f1 | sort -u | tr '\n' ' ')
  fi
  bed_contigs=$(cut -f1 "$TBED" 2>/dev/null | sort -u | tr '\n' ' ')
  echo "    reference contigs : ${ref_contigs:-<none>}"
  echo "    truth VCF contigs : ${vcf_contigs:-<none>}"
  echo "    truth BED contigs : ${bed_contigs:-<none>}"

  # Do they share the chr20 naming? Flag if one uses 'chr20' and another bare '20'.
  has_chr=$(printf '%s %s %s' "$ref_contigs" "$vcf_contigs" "$bed_contigs" | grep -c 'chr20' || true)
  has_bare=$(printf '%s %s %s' "$ref_contigs" "$vcf_contigs" "$bed_contigs" | grep -Ec '(^| )20( |$)' || true)
  if [ "$has_chr" -gt 0 ] && [ "$has_bare" -gt 0 ]; then
    bad "contig-name MISMATCH: some inputs use 'chr20', others use bare '20' — hap.py will report ~0 true positives. Normalize them (see docs/RUNBOOK.md)."
  else
    ok "contig naming looks consistent"
  fi
fi

echo ""
if [ "$fail" -gt 0 ]; then
  echo "✗ preflight: $fail blocker(s), $warn warning(s) — resolve blockers before running."; exit 1
elif [ "$warn" -gt 0 ]; then
  echo "! preflight: ready for the -stub run; stage data + reads for a real run ($warn warning(s))."; exit 0
else
  echo "✓ preflight: ready for a real run."; exit 0
fi
