# Glossary

Decoder ring for acronyms, terms, and codenames used in this repo's planning docs
(`docs/ROADMAP.md`, `docs/MILESTONES.md`, `.planning/ROADMAP.md`) and its CLAUDE.md.
Not a restatement of TASKS.md — see that file for the actual open-item list.

| Term | Meaning |
|---|---|
| GIAB HG002 / NA24385 | Genome in a Bottle reference sample used as the truth set for this project's germline SNV validation; scope locked to GRCh38 chr20 (ADR-0001). |
| hap.py | Benchmarking tool that compares called variants against the GIAB truth set (xcmp comparison engine, per ADR-0015) and reports precision/recall/F1. |
| SNV F1 / precision / recall | Standard variant-calling accuracy metrics from the hap.py comparison; project's acceptance criterion is SNV F1 ≥ 0.99. |
| Ti/Tv | Transition/transversion ratio, a QC metric reported alongside precision/recall/F1 in `docs/VALIDATION.md`. |
| ADR | Architecture Decision Record — append-only file under `docs/adr/`; a decision is recorded as a new next-numbered ADR, never edited in place, only superseded. |
| Kiro spec | An AI-assisted planning feature of the Kiro IDE, used to develop this project. Tracked separately in `.kiro/specs/clinical-genomics-platform/tasks.md`. Owns the serverless infrastructure migration (Lambda + Step Functions + DynamoDB) and the RAG reporter (FAISS + Ollama) — these are explicitly NOT re-planned in `docs/ROADMAP.md` or `.planning/ROADMAP.md`. |
| CDK | AWS Cloud Development Kit (TypeScript) — defines the 6 stacks under `infra/lib/`; guardrail tests live in `infra/test/`. |
| DynamoDB vs Postgres primary-store question | ADR-0012 made DynamoDB the primary metadata store (superseding ADR-0005's insert-only Postgres), with Postgres demoted to a Metabase read-bridge fed by a DynamoDB→Postgres sync. `.planning/ROADMAP.md` Phase 2 flags that the DynamoDB primary's tamper-evidence is IAM-based (bypassable by a table admin/root), weaker than Postgres's trigger-based enforcement — an open integrity gap. |
| nf-core lint / nf-test | nf-core is the Nextflow community's pipeline conventions; `nf-core lint` checks conformance, `nf-test` is its module/workflow test framework. Neither is yet fully in place here — this is the one open item (P1-1) in `docs/ROADMAP.md`. |
| MiXCR / AIRR | MiXCR is an immune-repertoire (TCR/BCR) sequence analysis tool; AIRR is the adaptive-immune-receptor-repertoire data standard. Planned as a second assay modality (P2-1 in `docs/ROADMAP.md`) reusing the existing pipeline spine, gated behind a new `--assay {snv,airr}` selector. |
| M0–M8 | Milestone codenames in `docs/MILESTONES.md` tracking the platform's build order: M0 repo scaffold/stub DAG, M1 core pipeline, M2 hap.py validation + provenance stamp, M3 Docker/CI, M4 CDK serverless orchestration, M5 Postgres ingestion, M6 Metabase dashboard, M7 QLoRA fine-tune + review flag, M8 README/VALIDATION/demo GIF/resume bullets. All marked complete. |
| Phase 1: Execution Substrate Decision | `.planning/ROADMAP.md` phase 1 — record one authoritative ADR for where real genomics compute runs (AWS Batch vs. HealthOmics vs. other), reconcile all docs that currently reference AWS Batch. First phase; everything else depends on it. |
| Phase 2: Machine-Verified Integrity | `.planning/ROADMAP.md` phase 2 — make the blocking-CI posture and tamper-evidence guarantee true for the DynamoDB primary store (not just the Postgres replica); strengthen CDK guardrail tests and DB trigger CI checks so they can actually fail a merge. |
| Phase 3: Full-Scope Validation Evidence | `.planning/ROADMAP.md` phase 3 — measure SNV F1 over the full locked chr20 scope at representative (~30–40×) depth (current evidence is unrepresentative 255.8× depth); record honestly, including a downsampled-depth run. |
| Phase 4: Documentation Accuracy | `.planning/ROADMAP.md` phase 4 — bring CLAUDE.md's ADR count and primary-store claims, `docs/adr/README.md`'s index, and dangling ADR cross-references (e.g. ADR-0014) back in line with reality. |
| Phase 5: Reviewer Clickthrough | `.planning/ROADMAP.md` phase 5 — verify the three-minute Streamlit demo clickthrough works end-to-end and surfaces the Phase 3 measured numbers plus the AI-DRAFTED guardrail banners. |
| P0–P3 (docs/ROADMAP.md) | Older roadmap's phase labels: P0 = do now (highest-credibility items), P1 = near-term finish-what's-started, P2 = MiXCR multi-omic branch, P3 = later/roadmap-only (spatial genomics). Distinct from the Phase 1–5 naming in `.planning/ROADMAP.md`. |
| enforce_guardrails() | Function in `ai-report/infer.py` that stamps every AI-drafted report with the mandatory `AI-DRAFTED — REQUIRES CLINICIAN REVIEW` banner, a provenance line, and scrubs advice-phrasing, before a human signs off (ADR-0008). |
| Insert-only / append-only | Design rule: `runs`, `qc_metrics`, `run_provenance`, `audit_log` tables reject UPDATE/DELETE via DB triggers (`forbid_mutation()`); a correction is always a new row (ADR-0005, now nuanced by ADR-0012's DynamoDB-primary change). |
| Provenance stamp | Metadata block (git commit, pipeline version, reference build, truth-set version, SHA-256 checksums) built into every `metrics.json` by `pipeline/bin/build_metrics.py`. Known gaps: checksums cover only derived artifacts (not raw reads/reference/truth set), and no container digest/tool version reaches the stamp. |
