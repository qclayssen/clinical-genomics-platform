# ADR-0006 — Use Metabase for the operational dashboard

**Status:** Accepted · **Date:** 2026-05-17

## Context

The people who care about lab *operations* (a lab director, a quality manager) are typically
not programmers. They need an at-a-glance view — pass rates, turnaround time, quality trends
— that they can read and, ideally, filter themselves. The dashboard should also be
**version-controlled**, not clicked together once and lost.

## Decision

Use **Metabase** (open-source) connected to the results Postgres. Define every dashboard card
as **committed SQL** (`dashboards/metabase/README.md`) reading from a `v_run_summary` view,
so the dashboard is reproducible from the repo. Ship a `docker-compose.yml` that brings up
Postgres + Metabase together and a demo seed so the dashboard renders before any real run.

## Consequences

**Good**
- Non-technical stakeholders get a self-serve view without touching SQL.
- The dashboard is reproducible and reviewable because its queries live in git.
- One command (`docker compose up`) demonstrates the DB + dashboard layer.

**Bad / accepted limitations**
- Metabase is one more service to run; for a single-user demo it's heavier than a static
  chart, but it matches the "tool a lab actually uses" brief.
- Metabase's own internal state (drag-and-drop layout) still needs a serialization export to
  be fully captured in git; the SQL definitions are the durable source of truth.

## Alternatives considered

- **A static HTML report / matplotlib PNGs** — lighter, but not interactive and not the
  "ops dashboard a director opens daily" the brief calls for.
- **Grafana** — great for time-series/infra metrics, less suited to the business-intelligence,
  row-level reporting shape here.
- **Superset** — comparable to Metabase; Metabase chosen for a lower setup burden and a
  gentler experience for non-technical viewers.
