-- Row-level sandboxing without Metabase Enterprise
--
-- Metabase's native "Data Sandboxing" (row filtering keyed off a
-- per-user attribute) is a Pro/Enterprise-only feature. This file
-- demonstrates the equivalent pattern achievable with open-source
-- Metabase: a Postgres view that filters by current_user, one
-- least-privilege role per audience, and one Metabase database
-- connection + permission group per role. See ADR-0024 for the
-- full write-up and the tradeoffs against the real Enterprise feature.
--
-- Not applied by docker-entrypoint-initdb.d (it creates login roles with
-- passwords — a cluster-level, credential-bearing operation you don't want
-- firing on every container boot). Apply explicitly:
--   psql "$CGP_DB_URL" -f db/sandboxing_demo.sql

-- dim_sample_access: which Postgres role may see which sample_id's rows.
CREATE TABLE IF NOT EXISTS dim_sample_access (
    db_role   TEXT NOT NULL,
    sample_id TEXT NOT NULL REFERENCES samples(sample_id),
    PRIMARY KEY (db_role, sample_id)
);

-- A plain view (no security_invoker) runs against its underlying tables
-- with the *view owner's* privileges, while current_user still reflects
-- whoever is actually connected — so an analyst role can be granted SELECT
-- on this view alone, never on fact_run or dim_sample_access directly, and
-- still only ever see the rows dim_sample_access assigns to their role.
CREATE OR REPLACE VIEW v_fact_run_secured AS
SELECT f.*
FROM fact_run f
WHERE f.sample_id IN (
    SELECT sample_id FROM dim_sample_access WHERE db_role = current_user
);

-- Demo roles: two analyst cohorts, each scoped to a different subset of
-- samples. Password is a placeholder for local/demo use only — a real
-- deployment would use a secrets manager, not an inline literal.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cgp_analyst_cohort_a') THEN
        CREATE ROLE cgp_analyst_cohort_a LOGIN PASSWORD 'demo_only_change_me';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cgp_analyst_cohort_b') THEN
        CREATE ROLE cgp_analyst_cohort_b LOGIN PASSWORD 'demo_only_change_me';
    END IF;
END $$;

-- Grant SELECT on the secured view only — deliberately no grant on
-- fact_run, dim_sample_access, or any OLTP table, so there is no way to
-- read another cohort's rows short of a superuser escalation.
GRANT SELECT ON v_fact_run_secured TO cgp_analyst_cohort_a, cgp_analyst_cohort_b;

INSERT INTO dim_sample_access (db_role, sample_id) VALUES
    ('cgp_analyst_cohort_a', 'HG002_chr20'),
    ('cgp_analyst_cohort_a', 'HG003_chr20'),
    ('cgp_analyst_cohort_b', 'HG004_chr20'),
    ('cgp_analyst_cohort_b', 'NA12878_chr20')
ON CONFLICT DO NOTHING;
