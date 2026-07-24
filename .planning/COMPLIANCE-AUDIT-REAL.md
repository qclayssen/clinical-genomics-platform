# Compliance Audit Report - Real Analysis

**Date:** 2026-07-24T08:31:18Z  
**Agent:** Built-in `compliance-auditor` (with repo access)  
**Scope:** PRs #46, #47, #48, #49  
**Standards:** ISO 15189 / NATA traceability & validation patterns

---

## Executive Summary

| PR | Status | Critical Issues | Medium Issues | Compliance |
|----|--------|-----------------|---------------|------------|
| #46 Demo validation display | ✅ **PASS** | None | None | 6/6 criteria |
| #47 ADR-0017 execution substrate | ⚠️ **NEEDS_REVISION** | None | Re-validation rule scope gap | 5/6 criteria |
| #48 CI blocking checks | 🚫 **BLOCKED** | Immutability test weakened | None | 5/6 criteria |
| #49 Documentation alignment | ✅ **PASS** (minor fix) | None | Module count inconsistency | 6/6 criteria |

**Overall:** 🟡 **MODERATE RISK** - PR #48 has critical control regression that must be fixed before merge.

---

## Critical Finding: PR #48 Immutability Test Weakening

### Problem
`.github/workflows/db-ci.yml` lines 61-111 changed from **fail-fast** to **warning aggregation**:

**Before (blocking):**
```bash
if ! psql -c "UPDATE runs..." 2>&1 | grep -q "insert-only"; then
  echo "FAILED — UPDATE was not blocked!" && exit 1
fi
```

**After (non-blocking):**
```bash
if ! psql -c "UPDATE runs..." 2>&1 | grep -q "insert-only"; then
  echo "NOT BLOCKED (warning)"; PASS=false
fi
# ...later: "⚠️ Some triggers did not fire (non-blocking)"
```

### Impact
**HIGH** - The `forbid_mutation()` triggers in `db/schema.sql` are the secondary enforcement layer for insert-only integrity. A broken trigger could allow UPDATE/DELETE operations in the Postgres read-replica (Metabase), breaking audit trails and dashboard integrity.

### Fix Required
Revert to fail-fast behavior. Each immutability check must `exit 1` on failure.

---

## Medium Finding: Re-validation Rule Scope (ADR-0003)

### Problem
ADR-0003 says "any change to reference, caller, or filtering" triggers re-validation. **Compute substrate changes** (local → cloud, container versions, orchestration) do NOT trigger re-validation under this rule.

### Context
- ADR-0011 (Batch/Fargate → Lambda) did not trigger re-validation
- ADR-0017 (documents local Nextflow as sole compute) also does not trigger re-validation
- Different compute environments *could* theoretically affect results (CPU architecture, memory, kernel)

### Assessment
The rule is reasonable for a portfolio project, but should be **explicitly documented why** orchestration changes don't trigger re-validation (answer: algorithmic pipeline unchanged — same BWA-MEM2 params, same HaplotypeCaller settings).

### Fix Recommended
Add clarifying note to ADR-0003 explaining the boundary between algorithmic changes (trigger re-validation) vs. infrastructure changes (do not trigger).

---

## Minor Finding: Module Count Inconsistency (PR #49)

### Problem
- `CLAUDE.md` line 20: "11 modules"
- `docs/PRODUCTION-MIGRATION.md` line 41: "11 modules"  
- `docs/MILESTONES.md` line 22: "12 modules" ✓ (correct)

### Actual Count
**12 modules** verified in `pipeline/modules/`:
1. fastqc
2. fastp
3. bwa_mem2
4. mark_duplicates
5. qualimap
6. multiqc
7. haplotypecaller
8. deepvariant
9. happy
10. export
11. metadata_ingest
12. qc_warnings

### Fix Required
Update CLAUDE.md and PRODUCTION-MIGRATION.md to say "12 modules".

---

## Controls Verified Intact

✅ **Provenance completeness** - No changes to `build_metrics.py` or `main.nf`  
✅ **AI guardrails** - `enforce_guardrails()` unchanged, banner mandatory  
✅ **Model Card honesty** - Limitations section preserved  
✅ **Audit trail** - `audit_log` schema unchanged  
✅ **DynamoDB IAM deny** - No changes to IAM policies  
✅ **Container digest pinning** - No `latest` tags introduced  

---

## Recommendations by PR

### PR #46 (Demo validation display)
✅ **APPROVE** - No issues found. Strengthens validation transparency.

### PR #47 (ADR-0017 execution substrate)
⚠️ **REQUEST CHANGES** (medium priority)
1. Add clarifying note to ADR-0003 about re-validation scope
2. Verify ADR-0017 content after merge (follows append-only convention)

### PR #48 (CI blocking checks)
🚫 **BLOCK** (critical)
1. **MUST FIX:** Revert immutability test to fail-fast behavior
2. Each trigger test must `exit 1` on failure, not aggregate warnings

### PR #49 (Documentation alignment)
✅ **APPROVE** (with minor fix)
1. Update module count to "12 modules" in CLAUDE.md and PRODUCTION-MIGRATION.md

---

## Overall Compliance Health

**Status:** 🟡 MODERATE RISK  
**Blocker:** PR #48 critical control regression  
**Action:** Fix PR #48, then safe to merge all 4 PRs

**Models Used:** 1 (built-in `compliance-auditor` via `omniroute-paid-premium`)
