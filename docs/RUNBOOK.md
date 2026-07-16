# Runbook — running the pipeline for real (to get real validation numbers)

Goal: turn the placeholder `VALIDATION.md` table into **measured** precision/recall/F1 by
running the pipeline end-to-end on GIAB HG002 chr20. This runs on **your machine** (not CI);
it needs Nextflow + Docker + the staged data.

Estimated effort: ~30 min setup + one pipeline run (minutes to ~1–2 h depending on the data
slice and your hardware).

---

## 1. Install prerequisites

| Tool | Why | Install (macOS) | Check |
|---|---|---|---|
| Java 17+ | Nextflow runs on the JVM | `brew install temurin` | `java -version` |
| Nextflow | Runs the pipeline | `brew install nextflow` | `nextflow -version` |
| Docker | Runs each step in its pinned container | Docker Desktop | `docker info` |

> The pipeline pulls Biocontainers per step, so you don't install bwa-mem2/GATK/hap.py
> yourself — Docker does. Make sure Docker Desktop is running before you start.

## 2. Preflight check

Run the checker before staging data and again after — it verifies tools and, once data is
present, that reference / truth / reads use **consistent contig names** (the #1 cause of a
silently-wrong `hap.py` result):

```bash
./scripts/preflight.sh
```

## 3. Stage the real data

The tiny committed files are only for the `-stub` DAG. For real numbers, stage GIAB HG002
chr20:

```bash
./scripts/fetch_testdata.sh            # reference (GRCh38 chr20), GIAB truth VCF+BED
# Provide real HG002 chr20 reads as pipeline/assets/testdata/HG002_chr20_R{1,2}.fastq.gz
# (see the notes the script prints — subsample a public HG002 read set with seqtk if large)
./scripts/preflight.sh                 # re-run: now also checks contig consistency
```

## 4. Run

```bash
cd pipeline

# a. sanity: structure resolves (no tools/data needed)
nextflow run main.nf -profile test,docker -stub

# b. real run on the staged chr20 data
nextflow run main.nf -profile docker \
    --input assets/samplesheet.test.csv \
    --reference assets/reference/GRCh38_chr20.fa \
    --truth_vcf assets/truth/HG002_GRCh38_chr20_v4.2.1.vcf.gz \
    --truth_bed assets/truth/HG002_GRCh38_chr20_v4.2.1.bed \
    --outdir ../results

# c. (optional) run the other caller too, to report concordance
nextflow run main.nf -profile docker --caller deepvariant --outdir ../results_dv ...
```

## 5. Read the results

- Per-sample metrics: `results/HG002_chr20/export/HG002_chr20.metrics.json`
- hap.py summary: `results/HG002_chr20/validation/HG002_chr20.happy.summary.csv`
- Aggregate QC: `results/multiqc/multiqc_report.html`
- Provenance (timeline/trace/DAG): `results/provenance/`

The GA4GH refget identity of your reference (for provenance):
```bash
python3 pipeline/bin/ga4gh_ids.py --fasta pipeline/assets/reference/GRCh38_chr20.fa
```

## 6. Record the numbers honestly

Copy the **measured** precision/recall/F1 into `docs/VALIDATION.md` and the README table.
Note the exact truth version, reference build, and pipeline git commit alongside them
(they're already in `metrics.json` provenance). Per ADR-0003, a version bump should
re-run this validation.

---

## Troubleshooting

- **hap.py reports ~0 TP / everything FP:** almost always a **contig-name mismatch** — the
  query VCF says `20` but truth/reference say `chr20` (or vice-versa). `./scripts/preflight.sh`
  flags this. Fix by normalizing contig names (the fetch script normalizes the reference to
  `chr20`; ensure your reads align to that same reference).
- **Out of memory / killed:** lower the region, e.g. `--intervals chr20:1000000-2000000`, or
  raise `--max_memory`. DeepVariant is the heavier caller.
- **Docker not found / permission denied:** ensure Docker Desktop is running; `docker info`
  should succeed without sudo.
- **Slow first run:** container image pulls happen once; subsequent runs reuse them and
  Nextflow's `-resume` reuses completed steps.
