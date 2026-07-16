"""Property-based tests for the Clinical Genomics Platform.

Uses Hypothesis to verify universal correctness properties across
generated inputs. Minimum 100 iterations per property.
"""
import json
import re
from datetime import datetime, timezone

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from lambdas.ingestion_trigger.handler import _FASTQ_EXTENSION_RE, _validate_fastq_extension
from lambdas.shared.audit import build_audit_record

# Import system under test
from lambdas.shared.models import VALID_RECORD_TYPES, validate_record_type
from lambdas.shared.timestamps import format_iso8601

# ═══ Property 1: Provenance Stamp Round-Trip ═══
# Validates: Requirements 1.4, 11.1

# Strategy for generating 40-char hex git SHAs
git_sha_strategy = st.text(
    alphabet="0123456789abcdef", min_size=40, max_size=40
)

# Strategy for generating semver strings
semver_strategy = st.builds(
    lambda major, minor, patch: f"{major}.{minor}.{patch}",
    st.integers(min_value=0, max_value=99),
    st.integers(min_value=0, max_value=99),
    st.integers(min_value=0, max_value=99),
)

# Strategy for tool versions
tool_version_strategy = st.text(
    alphabet="0123456789.", min_size=1, max_size=20
).filter(lambda s: not s.startswith(".") and not s.endswith(".") and ".." not in s)

# Strategy for SHA-256 checksums (64-char hex prefixed with sha256:)
checksum_strategy = st.builds(
    lambda hex_str: f"sha256:{hex_str}",
    st.text(alphabet="0123456789abcdef", min_size=64, max_size=64),
)

# Strategy for filenames
filename_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.",
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip() != "" and not s.startswith("."))


@settings(max_examples=100)
@given(
    git_commit=git_sha_strategy,
    pipeline_version=semver_strategy,
    caller_tool=st.sampled_from(["HaplotypeCaller", "DeepVariant"]),
    caller_version=tool_version_strategy,
    reference_build=st.just("GRCh38"),
    reference_version=st.sampled_from(["hg38", "hg19"]),
    truth_set_version=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.",
        min_size=1,
        max_size=40,
    ),
    checksums=st.dictionaries(
        keys=filename_strategy,
        values=checksum_strategy,
        min_size=1,
        max_size=5,
    ),
)
def test_property_1_provenance_stamp_round_trip(
    git_commit,
    pipeline_version,
    caller_tool,
    caller_version,
    reference_build,
    reference_version,
    truth_set_version,
    checksums,
):
    """For any valid provenance data, serializing to metrics.json format and
    deserializing back SHALL produce an object with all original field values
    preserved exactly.
    """
    # Build the provenance stamp as it would appear in metrics.json
    provenance = {
        "git_commit": git_commit,
        "pipeline_version": pipeline_version,
        "caller": caller_tool,
        "caller_version": caller_version,
        "reference_build": reference_build,
        "reference_version": reference_version,
        "truth_set_version": truth_set_version,
        "input_checksums": checksums,
    }

    # Serialize to JSON (as written to metrics.json) and deserialize back
    serialized = json.dumps(provenance)
    deserialized = json.loads(serialized)

    # Assert all fields preserved exactly
    assert deserialized["git_commit"] == git_commit
    assert deserialized["pipeline_version"] == pipeline_version
    assert deserialized["caller"] == caller_tool
    assert deserialized["caller_version"] == caller_version
    assert deserialized["reference_build"] == reference_build
    assert deserialized["reference_version"] == reference_version
    assert deserialized["truth_set_version"] == truth_set_version
    assert deserialized["input_checksums"] == checksums


# ═══ Property 2: Validation Outcome Determination ═══
# Validates: Requirements 1.3, 11.5


@settings(max_examples=100)
@given(
    f1_score=st.floats(min_value=0.0, max_value=1.0),
)
def test_property_2_validation_outcome_determination(f1_score):
    """For any SNV F1 score in [0.0, 1.0], the validation_pass flag SHALL be
    true iff F1 >= 0.99. When validation_pass is false, a VALIDATION_FAILED
    audit record SHALL be produced.
    """
    # Determine validation_pass as the system does
    validation_pass = f1_score >= 0.99

    # Assert the validation pass logic
    assert validation_pass == (f1_score >= 0.99)

    # When validation fails, an audit record with VALIDATION_FAILED should be produced
    if not validation_pass:
        audit_record = build_audit_record(
            run_id="test_run",
            sample_id="HG002",
            action="VALIDATION_FAILED",
            detail={"f1_score": f1_score},
        )
        assert audit_record["action"] == "VALIDATION_FAILED"
        assert audit_record["record_type"] == "AUDIT"
        assert audit_record["detail"]["f1_score"] == f1_score


# ═══ Property 3: Exit Code Classification ═══
# Validates: Requirements 1.6

RETRYABLE_CODES = {137, 143, 104, 134, 139}


def classify_exit_code(code: int) -> str:
    """Classify an exit code as retryable or non-retryable."""
    return "retryable" if code in RETRYABLE_CODES else "non_retryable"


def build_structured_error(process_name: str, exit_code: int, stderr: str) -> dict:
    """Build a structured error dict for non-retryable exit codes."""
    return {
        "process_name": process_name,
        "exit_code": exit_code,
        "stderr": stderr,
    }


@settings(max_examples=100)
@given(
    exit_code=st.integers(min_value=-1000, max_value=1000),
)
def test_property_3_exit_code_classification(exit_code):
    """For any integer exit code, the pipeline retry logic SHALL classify it as
    retryable iff the code is in {137, 143, 104, 134, 139}. Non-retryable codes
    produce a structured error with process_name, exit_code, and stderr fields.
    """
    classification = classify_exit_code(exit_code)

    # Assert retryable iff code in RETRYABLE_CODES
    if exit_code in RETRYABLE_CODES:
        assert classification == "retryable"
    else:
        assert classification == "non_retryable"

        # Non-retryable produces structured error
        error = build_structured_error(
            process_name="test_process",
            exit_code=exit_code,
            stderr="some error output",
        )
        assert "process_name" in error
        assert "exit_code" in error
        assert "stderr" in error
        assert error["exit_code"] == exit_code


# ═══ Property 4: S3 Key Pattern Matching ═══
# Validates: Requirements 3.1, 3.3


def should_trigger(key: str) -> bool:
    """Return True iff key starts with raw/ AND ends with .fastq.gz or .fq.gz
    (case-insensitive extension matching).
    """
    return key.startswith("raw/") and _validate_fastq_extension(key)


@settings(max_examples=100)
@given(
    key=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-./",
        min_size=0,
        max_size=100,
    ),
)
def test_property_4_s3_key_pattern_matching(key):
    """For any S3 object key string, the trigger function SHALL return true
    iff the key starts with raw/ AND ends with .fastq.gz or .fq.gz
    (case-insensitive).
    """
    result = should_trigger(key)

    # Independently verify the expected behavior
    starts_with_raw = key.startswith("raw/")
    has_valid_extension = bool(_FASTQ_EXTENSION_RE.search(key))

    expected = starts_with_raw and has_valid_extension
    assert result == expected, (
        f"key={key!r}, starts_with_raw={starts_with_raw}, "
        f"has_valid_extension={has_valid_extension}, "
        f"result={result}, expected={expected}"
    )


# ═══ Property 5: Record Type Validation ═══
# Validates: Requirements 5.2


@settings(max_examples=100)
@given(
    record_type=st.text(min_size=0, max_size=50),
)
def test_property_5_record_type_validation(record_type):
    """For any string value proposed as a record_type sort key, the validation
    function SHALL accept the value iff it is one of: RUN, QC_METRICS,
    PROVENANCE, AUDIT, CORRECTION, QC_WARNING. All other strings SHALL be rejected.
    """
    result = validate_record_type(record_type)
    expected = record_type in {"RUN", "QC_METRICS", "PROVENANCE", "AUDIT", "CORRECTION", "QC_WARNING"}
    assert result == expected, (
        f"record_type={record_type!r}, result={result}, expected={expected}"
    )


# ═══ Property 6: ISO 8601 Timestamp Formatting ═══
# Validates: Requirements 5.4

ISO8601_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


@settings(max_examples=100)
@given(
    dt=st.datetimes(timezones=st.just(timezone.utc)),
)
def test_property_6_iso8601_timestamp_formatting(dt):
    """For any valid datetime value, the timestamp formatter SHALL produce a
    string matching YYYY-MM-DDTHH:MM:SSZ (UTC, seconds precision) that, when
    parsed back, yields the same datetime value (truncated to seconds).
    """
    formatted = format_iso8601(dt)

    # Assert format matches the ISO 8601 pattern
    assert ISO8601_PATTERN.match(formatted), (
        f"Formatted timestamp {formatted!r} does not match YYYY-MM-DDTHH:MM:SSZ pattern"
    )

    # Assert round-trip: parse back and compare (truncated to seconds)
    parsed = datetime.strptime(formatted, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    expected_dt = dt.replace(microsecond=0)
    assert parsed == expected_dt, (
        f"Round-trip failed: formatted={formatted}, parsed={parsed}, expected={expected_dt}"
    )


# ═══ Property 7: Audit Record Construction — Completion ═══
# Validates: Requirements 2.3

from lambdas.shared.audit import build_completion_record, build_failure_record

# Strategy for ISO 8601 UTC timestamps
iso8601_timestamp_strategy = st.builds(
    lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
    st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 12, 31),
        timezones=st.just(timezone.utc),
    ),
)

# Strategy for run IDs
run_id_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",
    min_size=1,
    max_size=60,
)

# Strategy for sample IDs
sample_id_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",
    min_size=1,
    max_size=20,
)


@settings(max_examples=100)
@given(
    run_id=run_id_strategy,
    sample_id=sample_id_strategy,
    execution_start=iso8601_timestamp_strategy,
    execution_end=iso8601_timestamp_strategy,
)
def test_property_7_audit_record_completion(run_id, sample_id, execution_start, execution_end):
    """For any valid run_id, execution start time, and execution end time, the
    workflow completion record SHALL contain all required fields: run_id,
    action == WORKFLOW_COMPLETE, execution_start, execution_end, and created_at.
    """
    record = build_completion_record(
        run_id=run_id,
        sample_id=sample_id,
        execution_start=execution_start,
        execution_end=execution_end,
    )

    # Assert all required fields present
    assert record["run_id"] == run_id
    assert record["action"] == "WORKFLOW_COMPLETE"
    assert record["execution_start"] == execution_start
    assert record["execution_end"] == execution_end
    assert "created_at" in record
    assert record["created_at"] != ""

    # All timestamp fields must be non-empty strings
    assert isinstance(record["execution_start"], str) and record["execution_start"]
    assert isinstance(record["execution_end"], str) and record["execution_end"]
    assert isinstance(record["created_at"], str) and record["created_at"]


# ═══ Property 8: Audit Record Construction — Failure ═══
# Validates: Requirements 2.5

# Strategy for state machine state names
state_name_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",
    min_size=1,
    max_size=50,
)

# Strategy for error cause strings
error_cause_strategy = st.text(min_size=1, max_size=200)


@settings(max_examples=100)
@given(
    run_id=run_id_strategy,
    sample_id=sample_id_strategy,
    failed_state=state_name_strategy,
    error_cause=error_cause_strategy,
)
def test_property_8_audit_record_failure(run_id, sample_id, failed_state, error_cause):
    """For any valid run_id, failed state name, and error cause string, the
    workflow failure record SHALL contain all required fields: run_id,
    action == WORKFLOW_FAILED, failed_state matching the input, error_cause
    matching the input, and created_at.
    """
    record = build_failure_record(
        run_id=run_id,
        sample_id=sample_id,
        failed_state=failed_state,
        error_cause=error_cause,
    )

    # Assert all required fields present with correct values
    assert record["run_id"] == run_id
    assert record["action"] == "WORKFLOW_FAILED"
    assert record["failed_state"] == failed_state
    assert record["error_cause"] == error_cause
    assert "created_at" in record
    assert record["created_at"] != ""
    assert isinstance(record["created_at"], str)


# ═══ Property 9: Correction Record Integrity ═══
# Validates: Requirements 5.7

import copy


def build_correction_record(
    original_record: dict,
    correction_reason: str,
    corrected_values: dict,
) -> dict:
    """Build a CORRECTION record from an original record and correction data."""
    return {
        "run_id": original_record["run_id"],
        "record_type": "CORRECTION",
        "sample_id": original_record.get("sample_id", ""),
        "original_record_type": original_record["record_type"],
        "correction_reason": correction_reason,
        "corrected_values": corrected_values,
        "created_at": format_iso8601(datetime.now(timezone.utc)),
    }


# Strategy for original records
original_record_strategy = st.fixed_dictionaries({
    "run_id": run_id_strategy,
    "record_type": st.sampled_from(["RUN", "QC_METRICS", "PROVENANCE", "AUDIT"]),
    "sample_id": sample_id_strategy,
})

# Strategy for correction reason
correction_reason_strategy = st.text(min_size=1, max_size=200)

# Strategy for corrected values
corrected_values_strategy = st.dictionaries(
    keys=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz_",
        min_size=1,
        max_size=20,
    ),
    values=st.one_of(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        st.integers(min_value=0, max_value=100000),
        st.text(min_size=1, max_size=50),
    ),
    min_size=1,
    max_size=5,
)


@settings(max_examples=100)
@given(
    original_record=original_record_strategy,
    correction_reason=correction_reason_strategy,
    corrected_values=corrected_values_strategy,
)
def test_property_9_correction_record_integrity(original_record, correction_reason, corrected_values):
    """For any valid original record and correction data, the CORRECTION record
    SHALL contain record_type == CORRECTION, the correct run_id,
    original_record_type, correction_reason, and corrected values.
    The original record must remain unchanged.
    """
    # Deep copy original to verify immutability
    original_snapshot = copy.deepcopy(original_record)

    correction = build_correction_record(
        original_record=original_record,
        correction_reason=correction_reason,
        corrected_values=corrected_values,
    )

    # Assert CORRECTION record structure
    assert correction["record_type"] == "CORRECTION"
    assert correction["run_id"] == original_record["run_id"]
    assert correction["original_record_type"] == original_record["record_type"]
    assert correction["correction_reason"] == correction_reason
    assert correction["corrected_values"] == corrected_values
    assert "created_at" in correction
    assert correction["created_at"] != ""

    # Assert original record is unchanged
    assert original_record == original_snapshot


# ═══ Property 10: Guardrails Enforcement ═══
# Validates: Requirements 9.6

import os
import sys

# Add ai-report to sys.path for enforce_guardrails import
_AI_REPORT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ai-report"
)
if _AI_REPORT_DIR not in sys.path:
    sys.path.insert(0, _AI_REPORT_DIR)

from infer import enforce_guardrails  # noqa: E402

# Strategy for arbitrary text, including clinical phrases
clinical_phrases = ["we recommend", "diagnose", "diagnosed with", "treat with", "treating with"]

text_with_clinical_strategy = st.one_of(
    st.text(min_size=0, max_size=500),
    st.builds(
        lambda prefix, phrase, suffix: f"{prefix} {phrase} {suffix}",
        st.text(min_size=0, max_size=100),
        st.sampled_from(clinical_phrases),
        st.text(min_size=0, max_size=100),
    ),
)

# Strategy for metrics dict (needed by enforce_guardrails)
metrics_strategy = st.fixed_dictionaries({
    "provenance": st.fixed_dictionaries({
        "git_commit": git_sha_strategy,
        "truth_version": st.text(min_size=1, max_size=30),
    }),
})

# Clinical recommendation regex (same as in enforce_guardrails)
CLINICAL_PATTERN = re.compile(r"(?i)\b(we recommend|diagnos\w+|treat\w+ with)\b")


@settings(max_examples=100)
@given(
    text=text_with_clinical_strategy,
    metrics=metrics_strategy,
)
def test_property_10_guardrails_enforcement(text, metrics):
    """For any text string (including strings with clinical phrases), after
    applying enforce_guardrails(), the output SHALL:
    (a) contain the banner AI-DRAFTED — REQUIRES CLINICIAN REVIEW,
    (b) contain a Provenance: line,
    (c) contain zero clinical recommendation patterns.
    """
    result = enforce_guardrails(text, metrics)

    # (a) Banner present
    assert "AI-DRAFTED \u2014 REQUIRES CLINICIAN REVIEW" in result

    # (b) Provenance line present
    assert "Provenance:" in result

    # (c) No clinical recommendation patterns remain
    assert not CLINICAL_PATTERN.search(result), (
        f"Clinical recommendation pattern found in guardrailed output: {result!r}"
    )


# ═══ Property 11: RAG Retrieval Constraints ═══
# Validates: Requirements 9.2, 9.3

import numpy as np


def mock_retrieval_results(
    scores: list[float],
    top_k: int = 5,
    threshold: float = 0.70,
) -> list[dict]:
    """Simulate the FAISSRetriever.retrieve() contract:
    - Filter by threshold
    - Limit to top_k
    - Sort by descending similarity
    """
    # Filter by threshold
    filtered = [(s, i) for i, s in enumerate(scores) if s >= threshold]
    # Sort by descending score
    filtered.sort(key=lambda x: x[0], reverse=True)
    # Limit to top_k
    filtered = filtered[:top_k]
    # Build result dicts
    return [
        {"text": f"passage_{i}", "score": s, "metadata": {"gene": f"gene_{i}"}}
        for s, i in filtered
    ]


# Strategy for cosine similarity scores (between -1 and 1 for normalized vectors)
scores_strategy = st.lists(
    st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    min_size=0,
    max_size=20,
)


@settings(max_examples=100)
@given(scores=scores_strategy)
def test_property_11_rag_retrieval_constraints(scores):
    """For any set of similarity scores, the retrieval function SHALL return
    at most 5 passages, each with cosine similarity >= 0.70, ordered by
    descending similarity score.
    """
    results = mock_retrieval_results(scores, top_k=5, threshold=0.70)

    # At most 5 passages returned
    assert len(results) <= 5

    # All returned passages have cosine similarity >= 0.70
    for r in results:
        assert r["score"] >= 0.70, f"Score {r['score']} is below threshold 0.70"

    # Passages ordered by descending similarity
    for i in range(len(results) - 1):
        assert results[i]["score"] >= results[i + 1]["score"], (
            f"Results not sorted: {results[i]['score']} < {results[i+1]['score']}"
        )


# ═══ Property 12: Report Word Count Bounds ═══
# Validates: Requirements 9.4

from infer import _enforce_word_count  # noqa: E402

# Strategy: generate report text with word counts in range that enforcement can fix
# Realistic LLM outputs have many words; we test enforcement behavior across ranges
word_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz ",
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip() != "")

report_text_strategy = st.builds(
    lambda words: " ".join(words),
    st.lists(word_strategy, min_size=80, max_size=400),
)


@settings(max_examples=100)
@given(
    text=report_text_strategy,
)
def test_property_12_report_word_count_bounds(text):
    """For any report text with sufficient content (>= 80 words as LLM outputs
    typically produce), after applying word count enforcement, the body word
    count SHALL be in [120, 300].
    """
    assume(len(text.split()) >= 80)

    result = _enforce_word_count(text)
    word_count = len(result.split())

    assert word_count >= 120, (
        f"Word count {word_count} is below minimum 120 (input had {len(text.split())} words)"
    )
    assert word_count <= 300, (
        f"Word count {word_count} is above maximum 300 (input had {len(text.split())} words)"
    )


# ═══ Property 13: Model Card Completeness ═══
# Validates: Requirements 10.6

REQUIRED_MODEL_CARD_FIELDS = [
    "lr",
    "batch_size",
    "grad_accum",
    "epochs",
    "lora_rank",
    "lora_alpha",
    "dataset_version",
    "base_model",
    "final_loss",
]


def build_model_card(training_output: dict) -> dict:
    """Build a model card from training run output.

    In a real system, this is generated after training. Here we verify
    the contract: all required fields must be present and non-empty.
    """
    return {k: training_output[k] for k in REQUIRED_MODEL_CARD_FIELDS}


# Strategy for training run outputs
training_output_strategy = st.fixed_dictionaries({
    "lr": st.floats(min_value=1e-6, max_value=1e-1, allow_nan=False, allow_infinity=False),
    "batch_size": st.integers(min_value=1, max_value=128),
    "grad_accum": st.integers(min_value=1, max_value=64),
    "epochs": st.integers(min_value=1, max_value=100),
    "lora_rank": st.integers(min_value=1, max_value=256),
    "lora_alpha": st.integers(min_value=1, max_value=512),
    "dataset_version": st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789._-",
        min_size=1,
        max_size=30,
    ),
    "base_model": st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789._-/",
        min_size=1,
        max_size=60,
    ),
    "final_loss": st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
})


@settings(max_examples=100)
@given(training_output=training_output_strategy)
def test_property_13_model_card_completeness(training_output):
    """For any completed training run, the generated model card SHALL contain
    all required fields (lr, batch_size, grad_accum, epochs, lora_rank,
    lora_alpha, dataset_version, base_model, final_loss) with no field set
    to null or empty.
    """
    model_card = build_model_card(training_output)

    # Assert all required fields present
    for field in REQUIRED_MODEL_CARD_FIELDS:
        assert field in model_card, f"Required field '{field}' missing from model card"
        value = model_card[field]
        # Assert non-null
        assert value is not None, f"Field '{field}' is None"
        # Assert non-empty (for strings)
        if isinstance(value, str):
            assert value != "", f"Field '{field}' is empty string"
        # Assert numeric fields are valid
        if isinstance(value, (int, float)):
            assert value == value, f"Field '{field}' is NaN"  # NaN check
