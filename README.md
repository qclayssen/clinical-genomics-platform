# Clinical Genomics Insight Platform

An end-to-end germline variant-calling platform: raw WGS reads → QC → alignment →
variant calling → **benchmarked against a truth set** → structured results in Postgres →
Metabase ops dashboard → an LLM that drafts a plain-language summary from the structured output.

Built to demonstrate the stack that clinical-bioinformatics / AWS-genomics roles screen for
(nf-core-style Nextflow, AWS CDK, provenance-tracked DB, BI dashboard, applied LLM), scoped
so a single person can finish it.

> ⚠️ **Scope honesty.** This is a portfolio project. It demonstrates the *validation methodology
> and traceability patterns* ISO 15189 / NATA accreditation requires (benchmarking against a
> reference truth set, insert-only provenance, audit trails, change control). It is **not** an
> accredited clinical test and must not be used for clinical decision-making. Wherever this
> project references ISO 15189, it means "built the patterns the standard asks for," not "certified."

> 🟢 **New to any of this?** Start with the plain-language
> **[Beginner's Guide](docs/BEGINNERS-GUIDE.md)** (what the whole thing does, no background
> assumed), and keep the **[Glossary](docs/GLOSSARY.md)** open — it defines every term below
> (FASTQ, VCF, hap.py, CDK, IAM, QLoRA…) in one line with an everyday analogy.

---

## Architecture

```
                 ┌───────────────────────────── AWS (via CDK) ─────────────────────────────┐
                 │                                                                          │
  FASTQ (GIAB    │   S3 data lake            AWS Batch                 CloudWatch           │
  HG002 chr20) ──┼─▶ raw/ ──▶ Nextflow ──▶ [ qc → align → call →      logs + alarms         │
                 │            (DSL2)          validate → export ]                           │
                 │                                    │                                     │
                 └────────────────────────────────────┼─────────────────────────────────────┘
                                                       │
                          metrics.json + Parquet + VCF │  (with full provenance stamp)
                                                       ▼
                                                 Postgres  ──▶  Metabase dashboard
                                                       │        (QC trends, turnaround,
                                                       │         validation pass/fail)
                                                       ▼
                                            ai-report (QLoRA-tuned LLM)
                                            structured JSON → draft summary
                                            (mandatory "requires review" flag)
```

## Validation summary

The pipeline is benchmarked on **GIAB HG002 / NA24385, chromosome 20** against the
v4.2.1 high-confidence truth set using `hap.py`. Real numbers land in
[`docs/VALIDATION.md`](docs/VALIDATION.md) after your first full run.

| Metric | GATK HaplotypeCaller | DeepVariant | Source |
|---|---|---|---|
| SNV precision | _run to fill_ | _run to fill_ | `hap.py` summary.csv |
| SNV recall | _run to fill_ | _run to fill_ | `hap.py` summary.csv |
| SNV F1 | _run to fill_ | _run to fill_ | `hap.py` summary.csv |
| Ti/Tv | _run to fill_ | _run to fill_ | `bcftools stats` |

## Quickstart

```bash
# 1. Stage the tiny test data (subset, ships in-repo) and run the stub DAG
cd pipeline
nextflow run main.nf -profile test,docker -stub

# 2. Full local run on GIAB HG002 chr20 (downloads inputs on first run)
nextflow run main.nf -profile test,docker

# 3. Deploy AWS infra and run the same pipeline on Batch
cd ../infra && npm ci && npx cdk synth && npx cdk deploy --all
cd ../pipeline && nextflow run main.nf -profile aws
```

See [`docs/SOP-run-pipeline.md`](docs/SOP-run-pipeline.md) for the operating procedure and
acceptance criteria.

## Repository layout

| Path | What's here |
|---|---|
| `pipeline/` | Nextflow DSL2 modules: QC → align → call → validate → export |
| `infra/` | AWS CDK app: S3 data lake, Batch compute, scoped IAM, CloudWatch |
| `db/` | Postgres schema + migrations (samples, runs, QC, provenance, audit) |
| `dashboards/metabase/` | Version-controlled dashboard + question definitions |
| `ai-report/` | **PyTorch** QLoRA fine-tune + inference for AI-drafted summaries ([model card](ai-report/MODEL_CARD.md)) |
| `docker/` | One pinned Dockerfile per pipeline stage |
| `docs/` | **Beginner's guide + glossary**, validation report, SOP, milestones |
| `docs/adr/` | **Architecture Decision Records** — why each choice was made |
| `tests/` | Unit tests + small committed fixtures (`tests/fixtures/`) |
| `.github/workflows/` | CI: nf-core lint, pipeline test profile, CDK synth, ML smoke test |

## Documentation map

- **New to the domain?** → [Beginner's Guide](docs/BEGINNERS-GUIDE.md) + [Glossary](docs/GLOSSARY.md)
- **Recruiter / hiring manager?** → [For Recruiters](docs/FOR-RECRUITERS.md)
- **Why these choices?** → [Architecture Decision Records](docs/adr/)
- **How accurate is it?** → [Validation Report](docs/VALIDATION.md)
- **The ML component?** → [Model Card](ai-report/MODEL_CARD.md) + [ADR-0007](docs/adr/0007-qlora-small-open-model.md)
- **How do I operate it?** → [SOP](docs/SOP-run-pipeline.md)

## Milestones

The build is demoable at every stage — see [`docs/MILESTONES.md`](docs/MILESTONES.md).

## License

MIT — see [`LICENSE`](LICENSE). Reference data (GIAB) is public domain / CC0 from NIST.
