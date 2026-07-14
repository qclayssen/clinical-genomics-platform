# Usage

How to provide inputs, choose parameters and profiles, and run the pipeline.

> This page is the reference for **inputs and parameters**. For the step-by-step operating
> procedure to produce **real, measured** validation numbers (installing tools, staging GIAB
> data, recording results), follow the [Runbook](RUNBOOK.md) instead — this page does not
> duplicate it. New to the domain? Start with the [Beginner's Guide](BEGINNERS-GUIDE.md) and
> keep the [Glossary](GLOSSARY.md) open.

## Samplesheet

The pipeline reads one paired-end WGS sample per row from a CSV passed via `--input`. The
column contract is enforced at runtime by [`pipeline/assets/schema_input.json`](../pipeline/assets/schema_input.json).

```csv
sample,fastq_1,fastq_2
HG002_chr20,assets/testdata/HG002_chr20_R1.fastq.gz,assets/testdata/HG002_chr20_R2.fastq.gz
```

| Column    | Required | Description                                                              |
|-----------|----------|--------------------------------------------------------------------------|
| `sample`  | yes      | Unique sample identifier. Used as `meta.id` and as the per-sample output folder name. Must contain no whitespace. |
| `fastq_1` | yes      | Path or URI to the gzipped R1 FASTQ. Must match `*.f(ast)q.gz`. Local paths are resolved relative to the launch directory; `s3://` URIs work under `-profile aws`. |
| `fastq_2` | yes      | Path or URI to the gzipped R2 FASTQ (same rules as `fastq_1`).           |

Two samplesheets ship in the repo:

- [`assets/samplesheet.test.csv`](../pipeline/assets/samplesheet.test.csv) — local test data,
  used by `-profile test`.
- [`assets/samplesheet.csv`](../pipeline/assets/samplesheet.csv) — a template pointing at
  `s3://your-bucket/raw/...`, the default `--input` for a non-test run.

## Parameters

Defaults live in [`pipeline/nextflow.config`](../pipeline/nextflow.config); the `test` profile
overrides several of them ([`conf/test.config`](../pipeline/conf/test.config)).

| Parameter          | Default                                             | Description |
|--------------------|-----------------------------------------------------|-------------|
| `--input`          | `assets/samplesheet.csv`                            | Samplesheet CSV (see above). |
| `--outdir`         | `<launchDir>/results`                               | Where published results are written. |
| `--reference`      | `assets/reference/GRCh38_chr20.fa`                  | Reference FASTA. Its `.*` sidecar index files are picked up automatically. |
| `--reference_build`| `GRCh38.p14`                                        | Reference build label, recorded in provenance. |
| `--truth_vcf`      | `assets/truth/HG002_GRCh38_chr20_v4.2.1.vcf.gz`     | GIAB high-confidence truth VCF for `hap.py`. |
| `--truth_bed`      | `assets/truth/HG002_GRCh38_chr20_v4.2.1.bed`        | GIAB high-confidence region BED. |
| `--truth_version`  | `GIAB-v4.2.1`                                        | Truth-set version label, recorded in provenance. |
| `--caller`         | `gatk`                                              | Variant caller: `gatk` (GATK4 HaplotypeCaller) or `deepvariant`. |
| `--intervals`      | _(profile-set; e.g. `chr20:1000000-2000000` in test)_ | Region to call over. Falls back to `chr20` if unset. |
| `--db_ingest`      | `false`                                             | Write results to Postgres (`DB_INGEST`). Set `true`, or use `-profile aws`. |
| `--db_url`         | `$CGP_DB_URL` or `postgresql://cgp:cgp@localhost:5432/cgp` | Postgres connection string used when `--db_ingest` is on. |
| `--max_cpus`       | `8`                                                 | Resource ceiling (clamped via `resourceLimits`). |
| `--max_memory`     | `16.GB`                                              | Resource ceiling. |
| `--max_time`       | `8.h`                                                | Resource ceiling. |

## Profiles

Combine profiles with commas (e.g. `-profile test,docker`).

| Profile      | Effect |
|--------------|--------|
| `test`       | Tiny committed inputs + a 1 Mb `--intervals` window so a full run is minutes-long. Sets `--input` to `assets/samplesheet.test.csv` and points reference/truth at the `assets/testdata/` placeholders. See [`conf/test.config`](../pipeline/conf/test.config). |
| `docker`     | Enables Docker so each step runs in its pinned container. Pass alongside `test` or on its own for a real local run. |
| `aws`        | Runs on AWS Batch, writing results/work to the S3 data lake and enabling DB ingest. Reads `CGP_S3_BUCKET`, `CGP_BATCH_QUEUE`, `CGP_DB_URL`, `AWS_REGION` from the environment; bucket/queue names come from the CDK stack outputs in `infra/`. See [`conf/aws.config`](../pipeline/conf/aws.config). |

There is no bundled `singularity`/`conda` profile — containers are Docker/Biocontainers, pinned
per step in the module `container` directives.

## Running

Run from the `pipeline/` directory.

```bash
# 1. Stub the full DAG — validates structure only, no tools or data needed
nextflow run main.nf -profile test -stub

# 2. Real local run on the test data (needs Docker)
nextflow run main.nf -profile test,docker

# 3. Real run on your own staged data
nextflow run main.nf -profile docker \
    --input assets/samplesheet.test.csv \
    --reference assets/reference/GRCh38_chr20.fa \
    --truth_vcf assets/truth/HG002_GRCh38_chr20_v4.2.1.vcf.gz \
    --truth_bed assets/truth/HG002_GRCh38_chr20_v4.2.1.bed \
    --outdir ../results

# 4. Try the alternative caller
nextflow run main.nf -profile test,docker --caller deepvariant

# 5. On AWS Batch (after `cdk deploy` and exporting the env vars above)
nextflow run main.nf -profile aws
```

Nextflow's `-resume` reuses completed steps; the config uses `cache = 'lenient'` so cached
results are reused only when inputs are byte-identical (provenance-friendly).

For producing and recording **measured** precision/recall/F1 on real GIAB data — including the
`scripts/preflight.sh` contig-consistency check and the honest-numbers workflow — see the
[Runbook](RUNBOOK.md). For the operating procedure and acceptance criteria (SNV F1 ≥ 0.99), see
the [SOP](SOP-run-pipeline.md).
