-- Demo seed data so the Metabase dashboard renders before you've run the pipeline.
-- Simulates a small cohort of runs across two pipeline versions. Safe to load into a
-- throwaway/demo DB only. Uses the same tables the real ingestion writes.

INSERT INTO samples (sample_id, reference_build) VALUES
  ('HG002_chr20','GRCh38.p14'),
  ('HG003_chr20','GRCh38.p14'),
  ('HG004_chr20','GRCh38.p14'),
  ('NA12878_chr20','GRCh38.p14')
ON CONFLICT DO NOTHING;

WITH demo(run_id, sample_id, ver, caller, started, exported, snp_p, snp_r, dup, nvar) AS (
  VALUES
    ('run_2026_0301_a','HG002_chr20','0.2.0','gatk',        TIMESTAMPTZ '2026-03-01 09:00', TIMESTAMPTZ '2026-03-01 10:12', 0.9981, 0.9964, 0.061, 61234),
    ('run_2026_0305_b','HG003_chr20','0.2.0','gatk',        TIMESTAMPTZ '2026-03-05 08:40', TIMESTAMPTZ '2026-03-05 09:55', 0.9975, 0.9958, 0.072, 60112),
    ('run_2026_0312_c','HG004_chr20','0.2.0','gatk',        TIMESTAMPTZ '2026-03-12 11:05', TIMESTAMPTZ '2026-03-12 12:30', 0.9962, 0.9901, 0.089, 59880),
    ('run_2026_0401_d','HG002_chr20','0.3.0','deepvariant', TIMESTAMPTZ '2026-04-01 09:15', TIMESTAMPTZ '2026-04-01 10:05', 0.9994, 0.9989, 0.058, 62010),
    ('run_2026_0405_e','NA12878_chr20','0.3.0','deepvariant',TIMESTAMPTZ '2026-04-05 14:20', TIMESTAMPTZ '2026-04-05 15:02', 0.9990, 0.9980, 0.064, 61540),
    ('run_2026_0409_f','HG003_chr20','0.3.0','deepvariant', TIMESTAMPTZ '2026-04-09 10:00', TIMESTAMPTZ '2026-04-09 10:44', 0.9987, 0.9975, 0.070, 60890)
)
, ins_run AS (
  INSERT INTO runs (run_id, sample_id, pipeline_version, git_commit, caller,
                    started_at, exported_at, validation_pass)
  SELECT run_id, sample_id, ver, 'demoseed', caller, started, exported,
         (snp_p*snp_r*2/(snp_p+snp_r)) >= 0.99
  FROM demo
  RETURNING id, run_id
)
INSERT INTO qc_metrics (run_pk, percent_duplication, snp_precision, snp_recall, snp_f1, n_variants)
SELECT ir.id, d.dup, d.snp_p, d.snp_r, (d.snp_p*d.snp_r*2/(d.snp_p+d.snp_r)), d.nvar
FROM demo d JOIN ins_run ir ON ir.run_id = d.run_id;
