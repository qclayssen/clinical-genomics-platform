# Output

What the pipeline writes under `--outdir` (default `results/`), and which module produces each
file. This matches the layout shown in the [end-to-end run evidence](END-TO-END.md) and the
[Runbook](RUNBOOK.md).

Most outputs are **per-sample**, published under `results/<sample>/…` (the `<sample>` folder is
the samplesheet `sample` value, e.g. `HG002_chr20`). Two directories — `multiqc/` and
`provenance/` — sit at the top level of `results/` because they aggregate across the run.

```
results/
├── <sample>/
│   ├── qc/
│   │   ├── fastp/        # fastp: trimmed reads + JSON/HTML report
│   │   └── fastqc/       # FastQC: per-read-file zip + HTML
│   ├── align/            # markduplicates BAM/metrics + bwa-mem2 log
│   ├── variants/         # called VCF (gatk or deepvariant) + index
│   ├── validation/       # hap.py benchmark vs. GIAB truth
│   └── export/           # structured metrics.json + Parquet
├── multiqc/              # aggregate QC report across steps
└── provenance/           # Nextflow run reports (timeline/report/trace/dag)
```

## `<sample>/qc/` — quality control

| Path | Produced by | Contents |
|------|-------------|----------|
| `qc/fastp/<sample>.fastp.json` | `FASTP` (`modules/qc/fastp.nf`) | Machine-readable trimming/quality summary (consumed by MultiQC). |
| `qc/fastp/<sample>.fastp.html` | `FASTP` | Human-readable fastp report. |
| `qc/fastp/<sample>.trim_{1,2}.fastq.gz` | `FASTP` | Adapter/quality-trimmed paired reads (input to alignment). |
| `qc/fastqc/*.zip`, `qc/fastqc/*.html` | `FASTQC` (`modules/qc/fastqc.nf`) | Per-read-file FastQC metrics (zip consumed by MultiQC). |

## `<sample>/align/` — alignment and duplicate marking

| Path | Produced by | Contents |
|------|-------------|----------|
| `align/<sample>.bwamem2.log` | `BWAMEM2_ALIGN` (`modules/align/bwamem2.nf`) | bwa-mem2 stderr log. Note: the intermediate sorted BAM is **not** published — only the log is — because the deduplicated BAM below supersedes it. |
| `align/<sample>.markdup.bam`, `align/<sample>.markdup.bai` | `MARKDUPLICATES` (`modules/align/markduplicates.nf`) | Duplicate-marked, indexed alignment (input to variant calling). |
| `align/<sample>.markdup.metrics` | `MARKDUPLICATES` | Picard MarkDuplicates metrics (duplication rate; feeds MultiQC and `metrics.json`). |

## `<sample>/variants/` — variant calls

Exactly one caller runs per sample, selected by `--caller`:

| Path | Produced by | Contents |
|------|-------------|----------|
| `variants/<sample>.gatk.vcf.gz` (+ `.tbi`) | `HAPLOTYPECALLER` (`modules/call/haplotypecaller.nf`), default | GATK4 HaplotypeCaller germline VCF + index. |
| `variants/<sample>.dv.vcf.gz` (+ `.tbi`) | `DEEPVARIANT` (`modules/call/deepvariant.nf`), when `--caller deepvariant` | DeepVariant germline VCF + index. |

## `<sample>/validation/` — analytical validation

| Path | Produced by | Contents |
|------|-------------|----------|
| `validation/<sample>.happy.summary.csv` | `HAPPY_BENCHMARK` (`modules/validate/happy_benchmark.nf`) | hap.py precision/recall/F1 by variant type vs. the GIAB truth set — the headline validation numbers. |
| `validation/<sample>.happy.extended.csv` | `HAPPY_BENCHMARK` | Stratified/extended hap.py metrics. |
| `validation/<sample>.happy.*` | `HAPPY_BENCHMARK` | Remaining hap.py artefacts (e.g. ROC tables). |

## `<sample>/export/` — structured, provenance-stamped output

| Path | Produced by | Contents |
|------|-------------|----------|
| `export/<sample>.metrics.json` | `JSON_METRICS` (`modules/export/json_metrics.nf`) | The canonical record: duplication + hap.py metrics joined with the full provenance stamp (git commit, pipeline/reference/truth versions, SHA-256 input checksums). Built by `pipeline/bin/build_metrics.py`. This is the only artefact the AI report ever sees. |
| `export/<sample>.metrics.parquet` | `PARQUET_EXPORT` (`modules/export/parquet_export.nf`) | The same record flattened one level into a single tabular row for dashboard/warehouse use. |

The `DB_INGEST` step (`modules/export/db_ingest.nf`, run only when `--db_ingest`/`-profile aws`)
does **not** publish a file to `results/` — it writes the metrics + VCF reference into the
insert-only Postgres schema; its `<sample>.ingest.log` stays in the Nextflow work directory.

## Top-level aggregates

| Path | Produced by | Contents |
|------|-------------|----------|
| `multiqc/multiqc_report.html` | `MULTIQC` (`modules/qc/multiqc.nf`) | Single HTML report aggregating fastp, FastQC, MarkDuplicates, and hap.py outputs across the run. |
| `multiqc/multiqc_data/` | `MULTIQC` | Parsed data tables backing the report. |
| `provenance/timeline.html` | Nextflow (`nextflow.config`) | Execution timeline of all tasks. |
| `provenance/report.html` | Nextflow | Resource-usage / run report. |
| `provenance/trace.txt` | Nextflow | Per-task trace (status, hashes, timings). |
| `provenance/dag.html` | Nextflow | Rendered workflow DAG. |

Downstream of these files, the same `metrics.json` flows into Postgres → the Metabase dashboard
and the AI report — see [END-TO-END.md](END-TO-END.md) for the full data flow.
