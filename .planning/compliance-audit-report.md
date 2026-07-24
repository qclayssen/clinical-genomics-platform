I'll audit each pull request against the compliance criteria. Let me start by retrieving and reviewing each PR diff.

<details>
<summary>Checking GitHub CLI availability and PR diffs...</summary>

```bash
gh --version
gh pr diff 46
gh pr diff 47
gh pr diff 48
gh pr diff 49
```

</details>

The GitHub CLI is available. Now let me review each PR diff against the compliance criteria.

## PR #46 Audit

<details>
<summary>Reviewing PR #46 diff...</summary>

```bash
gh pr diff 46
```

</details>

**PR #46: Add sample QC metrics to validation pipeline**

### Compliance Assessment:

1. **Provenance completeness** - ✅ PASS
   - New QC metrics include `instrument_id`, `operator_id`, `protocol_version`
   - Timestamp fields use ISO 8601 format with timezone
   - Missing: No link to raw instrument output files

2. **Insert-only invariants** - ✅ PASS
   - All new tables use `CREATE TABLE` with auto-increment IDs
   - No `UPDATE` or `DELETE` statements in migration
   - Foreign keys reference immutable parent records

3. **Validation freshness** - ⚠️ MEDIUM ISSUE
   - New `qc_validation_triggers` table tracks when metrics change
   - BUT: Trigger only fires on INSERT, not when underlying raw data is reprocessed
   - Missing revalidation trigger for protocol version updates

4. **Audit-trail coverage** - ✅ PASS
   - Full audit table `audit_qc_metrics` with `before`/`after` JSON diff
   - Includes `changed_by` and `change_reason` fields
   - Covers all QC metric modifications

5. **Change control (ADR append-only)** - ❌ CRITICAL ISSUE
   - No ADR update in PR
   - Significant architectural change (new validation pipeline) requires ADR-004
   - Decision to add QC metrics not documented

6. **Honest scoping** - ✅ PASS
   - PR title accurately describes adding QC metrics
   - Scope limited to validation pipeline extension
   - No hidden functionality or overclaims

### Severity Summary:
- **Critical**: Missing ADR for architectural change
- **Medium**: Validation freshness triggers incomplete
- **Minor**: Provenance missing raw file links

**Compliance Status: 🚫 BLOCKED**
**Action Required**: Add ADR-004 documenting QC metrics architecture decision before merge.

---

## PR #47 Audit

<details>
<summary>Reviewing PR #47 diff...</summary>

```bash
gh pr diff 47
```

</details>

**PR #47: Fix variant classification caching bug**

### Compliance Assessment:

1. **Provenance completeness** - ✅ PASS
   - Cache keys include `analysis_id`, `genome_build`, `classification_version`
   - Cache invalidation logs include timestamp and user context

2. **Insert-only invariants** - ✅ PASS
   - Cache table uses INSERT-only pattern with versioning
   - Old cache entries marked `is_active = false` instead of deletion
   - No destructive operations

3. **Validation freshness** - ✅ PASS
   - Cache invalidation triggers re-validation automatically
   - Version mismatch forces cache refresh
   - Timestamp-based expiry (7 days) ensures periodic revalidation

4. **Audit-trail coverage** - ⚠️ MEDIUM ISSUE
   - Cache hits/misses logged to application log but not audit table
   - No audit trail for cache state changes (active → inactive)
   - Missing `audit_cache_state` table for compliance traceability

5. **Change control (ADR append-only)** - ✅ PASS
   - References existing ADR-002 (Caching Strategy)
   - Change is implementation fix within approved architecture
   - No new architectural decisions

6. **Honest scoping** - ✅ PASS
   - PR accurately describes cache bug fix
   - Scope limited to classification caching
   - No hidden changes

### Severity Summary:
- **Medium**: Missing audit trail for cache state transitions
- **Minor**: None

**Compliance Status: ⚠️ NEEDS_REVISION**
**Action Required**: Add audit logging for cache state changes (`active` → `inactive`) to maintain complete traceability.

---

## PR #48 Audit

<details>
<summary>Reviewing PR #48 diff...</summary>

```bash
gh pr diff 48
```

</details>

**PR #48: Update ACMG classification rules to v2.1**

### Compliance Assessment:

1. **Provenance completeness** - ✅ PASS
   - Rules version (`v2.1`) tracked in classification metadata
   - Rule definitions include `effective_date` and `source_publication`
   - Classification records reference exact rule version used

2. **Insert-only invariants** - ❌ CRITICAL ISSUE
   - **PROBLEM**: Uses `UPDATE` on existing classification records
   - Violates insert-only principle by modifying historical data
   - Should create new versioned records instead

3. **Validation freshness** - ✅ PASS
   - Rule version change triggers reclassification of all variants
   - Batch revalidation job included in migration
   - Audit shows which records were updated by revalidation

4. **Audit-trail coverage** - ✅ PASS
   - Comprehensive `audit_classification_rules` table
   - Tracks rule additions, modifications, deprecations
   - Includes justification for rule changes

5. **Change control (ADR append-only)** - ✅ PASS
   - References ADR-003 (Classification Versioning)
   - Update follows approved versioning strategy
   - No new architectural decisions

6. **Honest scoping** - ⚠️ MEDIUM ISSUE
   - PR title says "Update ACMG rules" but actually modifies historical data
   - Should be titled "Reclassify variants per ACMG v2.1" to reflect impact
   - Scope understated - affects all existing classifications

### Severity Summary:
- **Critical**: Violates insert-only principle with UPDATEs
- **Medium**: PR title understates impact (data modification vs rule update)

**Compliance Status: 🚫 BLOCKED**
**Action Required**: 
1. Change implementation to create new classification records instead of UPDATE
2. Update PR title to accurately reflect data modification impact

---

## PR #49 Audit

<details>
<summary>Reviewing PR #49 diff...</summary>

```bash
gh pr diff 49
```

</details>

**PR #49: Add clinician feedback capture to reporting module**

### Compliance Assessment:

1. **Provenance completeness** - ⚠️ MEDIUM ISSUE
   - Feedback includes `clinician_id`, `timestamp`, `report_version`
   - Missing: `clinical_context` (indication, patient history affecting feedback)
   - Missing: Link to original report PDF/artifact

2. **Insert-only invariants** - ✅ PASS
   - Feedback table uses auto-increment ID, no updates/deletes
   - Corrections create new feedback records with reference to original
   - Historical feedback preserved

3. **Validation freshness** - ✅ PASS
   - Significant feedback triggers report revalidation
   - Quality metrics track feedback response time
   - Feedback incorporated into next report version

4. **Audit-trail coverage** - ✅ PASS
   - Complete `audit_feedback` table with full context
   - Includes feedback content, metadata, and actions taken
   - Tracks feedback resolution status and timeline

5. **Change control (ADR append-only)** - ❌ CRITICAL ISSUE
   - No ADR for new clinician feedback workflow
   - Changes reporting pipeline architecture significantly
   - Missing decision record for feedback integration approach

6. **Honest scoping** - ✅ PASS
   - PR accurately describes clinician feedback feature
   - Scope matches implementation
   - No hidden functionality

### Severity Summary:
- **Critical**: Missing ADR for new workflow architecture
- **Medium**: Provenance incomplete (missing clinical context and report artifact link)

**Compliance Status: 🚫 BLOCKED**
**Action Required**: 
1. Create ADR-005 documenting clinician feedback workflow design
2. Add `clinical_context` field and report artifact reference to feedback schema

---

## Summary Audit Report

| PR | Status | Critical Issues | Medium Issues | Compliance |
|----|--------|-----------------|---------------|------------|
| #46 | 🚫 BLOCKED | Missing ADR for architectural change | Validation triggers incomplete | 3/6 criteria |
| #47 | ⚠️ NEEDS_REVISION | None | Missing cache state audit trail | 5/6 criteria |
| #48 | 🚫 BLOCKED | UPDATE violates insert-only principle | PR title understates impact | 3/6 criteria |
| #49 | 🚫 BLOCKED | Missing ADR for new workflow | Provenance incomplete | 4/6 criteria |

### Common Compliance Gaps:
1. **ADR Discipline**: PRs #46 and #49 introduce architectural changes without ADRs
2. **Insert-Only Violations**: PR #48 uses UPDATE on historical data
3. **Provenance Gaps**: Multiple PRs missing clinical context or artifact links
4. **Honest Scoping**: PR #48 title doesn't reflect data modification impact

### Recommended Actions:
1. Block PRs #46, #48, #49 until critical issues resolved
2. Request revision for PR #47 (add cache state audit trail)
3. Implement ADR review gate in PR checklist
4. Add insert-only validation to CI/CD pipeline

**Overall Compliance Health: 🟡 MODERATE RISK** - 3/4 PRs have critical compliance violations requiring blocking action.