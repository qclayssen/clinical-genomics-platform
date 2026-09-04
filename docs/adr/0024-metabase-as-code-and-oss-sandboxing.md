# ADR-0024 — Metabase as code, OSS row sandboxing, and when a custom driver would be worth it

**Status:** Accepted (manifest + provisioning script + sandboxing, implemented) · **Date:** 2026-09-05

## Context

[ADR-0023](0023-star-schema-warehouse-airflow.md) added a warehouse layer and
more Metabase cards, but everything about *using* Metabase in this repo still
assumes a human clicking through its UI: the README tells you which SQL to
paste into a Native Question, one card at a time, and "exporting for version
control" meant running Metabase's serialization CLI (`metabase.jar export`)
against a live instance and copying the output in by hand — a step that had
never actually been run, since it requires a live Metabase instance this
sandboxed environment doesn't have (no Docker daemon available).

Two gaps that matter for demonstrating actual Metabase depth, not just SQL
authored for it:

1. Nothing in the repo treats the *dashboard itself* — the database
   connection, collections, cards, embedding config — as a versioned,
   reproducible artifact you could stand up from scratch with one command.
2. Nothing demonstrates governance/access control, which matters more for a
   clinical/PHI-adjacent platform than another chart. Metabase's own answer
   to "different audiences should see different rows" — Data Sandboxing — is
   a Pro/Enterprise-only feature, and this repo runs open-source Metabase
   (the `metabase/metabase` image in `docker-compose.yml`).

## Decision

**1. `dashboard_manifest.yaml` is now the single source of truth for cards.**
`dashboards/metabase/dashboard_manifest.yaml` declares the database
connection, two collections ("CGP Ops", "CGP Analytics"), and all ten cards
from ADR-0023 as data (name, SQL, display type) instead of only as prose in
a README.

**2. `provision_metabase.py` builds the dashboard from that manifest via the
REST API.** `MetabaseClient` wraps `/api/session`, `/api/database`,
`/api/collection`, `/api/card`, and `/api/dashboard`, and every
`get_or_create_*` method checks by name before creating — safe to re-run
against an existing instance, the way `db/sync_dynamodb_to_postgres.py` is
idempotent by `run_id`. It also turns on signed embedding
(`enable_embedding` + `embedding_params`) on the Ops dashboard, which is
what you'd actually flip on to embed this in an internal ops tool. This is
the thing "export the dashboard so it lives in git" was gesturing at in the
old README — instead of committing an opaque export blob produced by a tool
that was never actually run here, the human-readable manifest *is* the
committed artifact, and the script is how you'd turn it into a running
dashboard.

**3. Row sandboxing via Postgres views + per-role Metabase connections, not
Metabase Enterprise.** `db/sandboxing_demo.sql` adds `dim_sample_access`
(which Postgres role may see which `sample_id`) and `v_fact_run_secured`, a
plain (non-`security_invoker`) view that filters `fact_run` by
`current_user` against that mapping table while running with the view
owner's privileges — so an analyst role can be granted `SELECT` on the view
alone, never on `fact_run` or the mapping table directly, and current_user
still resolves to whoever is actually connected. Two demo roles
(`cgp_analyst_cohort_a`, `cgp_analyst_cohort_b`) each see only their
assigned samples; querying `fact_run` directly as either role fails with a
permission error. In Metabase terms: this is one Postgres connection per
role, each assigned to its own Metabase permission group — the OSS-achievable
approximation of what Enterprise Sandboxing does natively with a single
shared connection and per-user attributes.

**4. A custom driver is not worth building here — noted for when it would
be.** Metabase's driver SDK (`metabase.driver` multimethods, a
`plugins/` JAR) is the right tool when a source has no existing driver:
a proprietary LIMS/instrument API, a lab information system exposing only a
REST endpoint, or a GA4GH-style refget service ([ADR-0010](0010-ga4gh-standards-alignment.md))
that a lab wants queryable alongside Postgres in the same tool. This
platform's only data source is Postgres, which Metabase already drives
natively — so the honest answer here is a design note, not code: the
trigger for reaching for the driver SDK is "the source isn't SQL and isn't
already supported," and until this repo has such a source, building one
would be complexity with no data to point it at.

## Consequences

**Good**
- The manifest + script make the dashboard buildable from nothing but a
  fresh Metabase instance and one command, instead of a checklist a human
  has to follow card-by-card — this is the actual "infrastructure as code"
  claim, not just SQL committed to git.
- The sandboxing pattern is real, tested (see verification below), and
  transfers directly to a team on OSS Metabase who can't justify an
  Enterprise license but still needs per-audience row restriction.
- All of it is additive: nothing in ADR-0023's cards, `fact_run`, or the
  existing README setup steps changes. `sandboxing_demo.sql` is a separate,
  explicitly-applied file, not part of `docker-entrypoint-initdb.d`.

**Bad / accepted limitations**
- `provision_metabase.py` has never been run against a live Metabase in
  this environment — no Docker daemon is available here. Its correctness is
  argued from unit tests (`tests/test_provision_metabase.py`) that mock the
  REST API and assert on the exact request payloads Metabase's documented
  API expects, not from an end-to-end run. This is the same "needs
  environment" caveat as `infra/` needing a real AWS account.
- The sandboxing SQL *was* verified end-to-end: applied against a
  disposable local Postgres, confirmed `cgp_analyst_cohort_a` and
  `cgp_analyst_cohort_b` each see only their assigned `sample_id`s through
  `v_fact_run_secured`, and confirmed both get `permission denied` querying
  `fact_run` or `dim_sample_access` directly.
- View-based row filtering is a real, long-standing Postgres pattern, but it
  is not literally Metabase Sandboxing — there's no per-user-attribute UI in
  Metabase driving it, and adding a third cohort means a new Postgres role
  and a new Metabase connection, not a row in an admin screen. Worth being
  precise about this distinction in an interview rather than overclaiming
  parity with the Enterprise feature.
- The demo roles' passwords are inline placeholders (`demo_only_change_me`)
  for local/demo use only, flagged in the SQL comments — a real deployment
  would provision these from a secrets manager, not a committed literal.

## Alternatives considered

- **Commit a real Metabase serialization export** — rejected: doing this
  honestly requires actually running `metabase.jar export` against a live
  instance, which this environment cannot do (no Docker daemon). Committing
  a hand-authored file claiming to be that export's output would be exactly
  the kind of fabricated artifact this project's honesty conventions
  (README scope-honesty note, `docs/MILESTONES.md`) exist to avoid. The
  manifest is the honest middle ground: a real, readable, testable
  artifact that the script can turn into that same export.
- **Metabase Enterprise trial for real Sandboxing** — would demonstrate the
  actual feature UI, but ties a portfolio artifact to a licensed product a
  reader can't run themselves, and this project's whole design (ADR-0017)
  is that anyone can clone and run it. The Postgres-view approach runs on
  the same free `postgres:16` and `metabase/metabase` images already in
  `docker-compose.yml`.
- **Row-Level Security (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`) on
  `fact_run` directly** — RLS policies apply to base tables, not
  materialized views, so this doesn't work on `fact_run` as-is; and even on
  a base table, RLS combined with a `security_invoker` view would require
  granting analyst roles direct `SELECT` on the underlying table for the
  invoker view to function — which defeats the point, since they could then
  query the base table directly instead of going through the view. The
  plain (definer-style) view sidesteps this entirely.
