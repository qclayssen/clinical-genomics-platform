# Non-Negotiable Design Rules

These rules apply to ALL changes in this repository.

## Insert-only results/provenance

`runs`, `qc_metrics`, `run_provenance`, `audit_log` are append-only; DB triggers (`forbid_mutation()`) reject UPDATE/DELETE. A correction is a *new* run row, never an edit.

References: #[[file:db/schema.sql]], #[[file:docs/adr/0005-insert-only-postgres.md]]

## Every result carries a provenance stamp

Git commit, pipeline/tool/reference/truth-set versions, and SHA-256 checksums of all inputs — built into `metrics.json` by `pipeline/bin/build_metrics.py` and threaded from `main.nf`. Never remove fields from it.

## AI output always passes enforce_guardrails()

Mandatory `AI-DRAFTED — REQUIRES CLINICIAN REVIEW` banner, provenance line, and advice-phrase scrubbing — then a human signs off. The model only ever sees `metrics.json`, never raw reads or the VCF body.

References: #[[file:ai-report/infer.py]], #[[file:docs/adr/0008-guardrails-human-in-the-loop.md]]

## Decisions are ADRs, append-only

Record a new choice as the next-numbered file in `docs/adr/`; never rewrite an old one — supersede it and update its status.

## Re-validate on change

Any change to reference, caller, or filtering re-triggers the `hap.py`-vs-GIAB validation before tagging. Acceptance criterion: **SNV F1 ≥ 0.99**.

References: #[[file:docs/VALIDATION.md]], #[[file:docs/adr/0003-truth-set-validation.md]]
