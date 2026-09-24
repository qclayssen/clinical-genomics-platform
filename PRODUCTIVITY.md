# Productivity Memory

## Project
Clinical Genomics Insight Platform — portfolio germline-SNV variant-calling platform (see repo CLAUDE.md for full onboarding).

## Active roadmap
`.planning/ROADMAP.md` is the current active plan: 5 phases (Execution Substrate Decision →
Machine-Verified Integrity → Full-Scope Validation Evidence → Documentation Accuracy →
Reviewer Clickthrough), none started as of writing. Phase order matters because of real
dependencies — Phase 1 settles the one open architectural question everything else builds
on, Phase 2 is a CI/integrity prerequisite for re-validating, Phase 3 produces the measured
evidence, and Phases 4–5 depend on Phase 3's numbers being real before documenting/demoing
them. See `memory/projects/roadmap-v1-credibility-gaps.md`.

## Legacy roadmap
`docs/ROADMAP.md` (the older P0–P3 plan) is mostly done: all of P0 and most of P1 are
complete (real GIAB validation numbers, ADR supersessions, README diagram + demo GIFs, public
repo). The one open item is **P1-1** (nf-core lint / nf-test / real `versions.yml`
collation). P2 (MiXCR immune-repertoire branch) and P3 (spatial genomics, ADR-only) are
future work, not yet started. See `memory/projects/docs-roadmap-legacy.md`.

## Terms
See `memory/glossary.md` for the full decoder-ring table. A few load-bearing ones:
- **Kiro spec** — a separate AI-assisted planning track (`.kiro/specs/`) that owns the
  serverless migration and RAG reporter; neither roadmap above re-plans that work.
- **hap.py** — the tool benchmarking called variants against the GIAB truth set; SNV F1 is
  the project's headline accuracy metric (acceptance criterion ≥ 0.99).
- **ADR** — Architecture Decision Record, append-only under `docs/adr/`; corrections are new
  ADRs that supersede old ones, never edits.

## Preferences
No user preferences captured yet — this file grows as work happens.
