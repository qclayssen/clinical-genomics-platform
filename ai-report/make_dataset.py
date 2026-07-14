#!/usr/bin/env python3
"""Generate synthetic (metrics.json -> summary) training pairs.

Bootstraps a fine-tuning dataset by sampling plausible QC/validation numbers and
rendering a matching gold summary with a deterministic template. In practice you
then hand-edit a subset for tone/quality — but this gives a consistent, guardrail-
compliant starting corpus that already models the required banner + citations.
"""
import argparse
import json
import random


def make_record(rng: random.Random) -> dict:
    sample = f"HG{rng.randint(2, 7):03d}_chr20"
    caller = rng.choice(["gatk", "deepvariant"])
    precision = round(rng.uniform(0.990, 0.9995), 4)
    recall = round(rng.uniform(0.985, 0.9990), 4)
    f1 = round(2 * precision * recall / (precision + recall), 4)
    dup = round(rng.uniform(0.04, 0.12), 3)
    nvar = rng.randint(58000, 63000)
    git = "".join(rng.choice("0123456789abcdef") for _ in range(7))
    passed = f1 >= 0.99

    metrics = {
        "sample": sample,
        "validation_pass": passed,
        "qc": {"percent_duplication": dup},
        "validation": {"snp": {"precision": precision, "recall": recall, "f1": f1}},
        "provenance": {
            "caller": caller, "git_commit": git, "truth_version": "GIAB-v4.2.1",
            "n_variants": nvar,
        },
    }

    verdict = (
        "The run met the F1 ≥ 0.99 acceptance threshold."
        if passed else
        "The run did NOT meet the F1 ≥ 0.99 acceptance threshold; results should not be "
        "used until reviewed."
    )
    summary = (
        f"AI-DRAFTED — REQUIRES CLINICIAN REVIEW\n\n"
        f"Sample {sample} was processed with the {caller} variant caller. "
        f"{verdict} "
        f"SNV precision was {precision*100:.1f}% (validation.snp.precision), "
        f"recall {recall*100:.1f}% (validation.snp.recall), and "
        f"F1 {f1*100:.1f}% (validation.snp.f1). "
        f"{nvar:,} variants were called (provenance.n_variants), with a duplication "
        f"rate of {dup*100:.1f}% (qc.percent_duplication) as a library-quality indicator. "
        f"No clinical interpretation of individual variants is provided.\n\n"
        f"Provenance: git {git}, GIAB-v4.2.1."
    )
    return {"input": json.dumps(metrics), "output": summary}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data/synth_report_pairs.jsonl")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    with open(args.out, "w") as fh:
        for _ in range(args.n):
            fh.write(json.dumps(make_record(rng)) + "\n")
    print(f"wrote {args.n} pairs to {args.out}")


if __name__ == "__main__":
    main()
