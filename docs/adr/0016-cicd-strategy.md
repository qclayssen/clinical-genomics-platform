# ADR-0016: Tiered CI/CD Strategy

**Status:** Accepted  
**Date:** 2026-07-16  
**Deciders:** Quentin Clayssen

## Context

The platform had basic CI (pipeline lint/stub, CDK synth, ML smoke tests) but lacked
security scanning, database validation, coverage reporting, container lifecycle
management, dependency automation, and release engineering. For a clinical genomics
platform, these are not nice-to-haves — they map directly to ISO 15189 change-control
and supply-chain security expectations.

## Decision

Implement a **three-tier CI/CD architecture** optimised for developer feedback speed,
thoroughness, and cost:

### Tier 1 — On Push (every commit, < 3 min)
| Workflow | Purpose |
|---|---|
| `lint.yml` | Ruff (Python) + tsc (TypeScript) — instant code quality |
| `security.yml` (pip-audit job) | Dependency vulnerability check against CVE databases |
| `pipeline-ci.yml` | Existing: Nextflow stub, unit tests (now with coverage), lambda imports |

### Tier 2 — On PR / Merge (~ 10 min)
| Workflow | Purpose |
|---|---|
| `security.yml` (trivy-repo job) | Full filesystem vulnerability scan, SARIF → Security tab |
| `db-ci.yml` | Schema apply, migration idempotency, seed data, immutability trigger tests |
| `docker.yml` | Build image, Trivy scan, push to GHCR (sha-tagged) |
| `coverage.yml` | PR comment with coverage delta, badge update on main |

### Tier 3 — Scheduled / Event-driven
| Workflow | Purpose |
|---|---|
| `maintenance.yml` | Weekly full Trivy + license compliance, auto-issue on failure |
| `release.yml` | Tag-triggered GitHub Release + versioned Docker image |
| Dependabot | Weekly PRs for pip, npm, GitHub Actions, Docker ecosystems |

## Rationale

**Speed vs thoroughness tradeoff.** Developers get lint + pip-audit feedback in under
30 seconds. Heavier scans (Trivy filesystem, Docker build, Postgres service container)
run only on PRs where the extra 5–10 minutes is acceptable.

**Cost: $0.** All tooling is free-tier: GitHub Actions (2,000 min/month on free plan),
Trivy (OSS), pip-audit (OSS), GHCR (free for public repos), Dependabot (built-in).

**Clinical domain signals:**
- Security scanning demonstrates supply-chain awareness (ISO 15189 §5.3)
- DB migration CI proves schema integrity is machine-verified, not trust-based
- Immutability trigger tests validate the provenance/audit design in automation
- License compliance protects against accidental GPL contamination in MIT codebase

**Release discipline.** Semver tags produce GitHub Releases with auto-generated
changelogs and versioned Docker images. This maps to change-control documentation
expectations in accredited environments.

## Consequences

- Every PR gets 6+ status checks — clear quality signal for reviewers
- Dependabot may generate PR noise; grouped minor/patch updates mitigate this
- Coverage badge requires a one-time Gist setup (documented in workflow comments)
- The `maintenance` workflow requires `issues: write` permission for auto-issue creation
- SARIF uploads require the repo to have GitHub Advanced Security (free for public repos)

## Alternatives Considered

| Alternative | Why rejected |
|---|---|
| CircleCI / GitLab CI | Adds vendor lock-in; GitHub Actions is native and free |
| Snyk for security | Free tier is limited; Trivy + pip-audit cover the same ground at $0 |
| Codecov for coverage | External service; shields.io + gist badge is self-contained |
| Renovate instead of Dependabot | More powerful but more complex; Dependabot is built-in |
| Monorepo CI (single workflow) | Slower feedback; tiered approach gives faster push-time results |
