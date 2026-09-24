"""Tests for the Variant Interpretation Assistant's REST endpoint.

Runs entirely against the fixture-backed FastAPI app. `/agent/variant-review`
is a thin adapter over the existing `ai-report/agent/` interpreter (ADR-0014);
sign-off reuses the existing `/runs/{run_id}/review-decisions` endpoint
(ADR-0019) rather than a new one, so it's covered by tests/test_api.py.
"""

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

KNOWN_RUN_ID = "run_2026_0301_a"


def test_variant_review_returns_guardrailed_assessment_with_trace():
    resp = client.post(
        "/agent/variant-review",
        json={"chrom": "chr20", "pos": 4699605, "ref": "G", "alt": "A", "gene": "PRNP", "run_id": KNOWN_RUN_ID},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["variant_key"] == "chr20:4699605:G>A"
    assert body["run_id"] == KNOWN_RUN_ID
    assert body["classification"]
    assert body["banner"] == "AI-DRAFTED VARIANT INTERPRETATION — REQUIRES CLINICAL GENETICIST REVIEW"
    assert body["guardrail_violations"] == []
    # Transparency is a deliberate design point: the trace must be present and detailed.
    assert len(body["agent_trace"]) > 0
    assert all("content" in step for step in body["agent_trace"])


def test_variant_review_defaults_genotype_and_gene():
    resp = client.post(
        "/agent/variant-review",
        json={"chrom": "chr20", "pos": 9999999, "ref": "A", "alt": "T", "run_id": KNOWN_RUN_ID},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["genotype"] == "heterozygous"
    assert body["gene"] == ""


def test_variant_review_signoff_uses_existing_review_decisions_endpoint():
    review_resp = client.post(
        "/agent/variant-review",
        json={"chrom": "chr20", "pos": 4699605, "ref": "G", "alt": "A", "gene": "PRNP", "run_id": KNOWN_RUN_ID},
    )
    assessment = review_resp.json()

    signoff_resp = client.post(
        f"/runs/{KNOWN_RUN_ID}/review-decisions",
        json={
            "variant_key": assessment["variant_key"],
            "classification": assessment["classification"],
            "decision": "approved",
            "reviewer": "j.smith",
            "comment": "Reviewed agent trace and evidence codes.",
        },
    )
    assert signoff_resp.status_code == 201
    body = signoff_resp.json()
    assert body["run_id"] == KNOWN_RUN_ID
    assert body["variant_key"] == assessment["variant_key"]
    assert body["reviewer"] == "j.smith"


def test_variant_review_rejects_unknown_backend():
    resp = client.post(
        "/agent/variant-review",
        json={"chrom": "chr20", "pos": 4699605, "ref": "G", "alt": "A", "run_id": KNOWN_RUN_ID, "backend": "watson"},
    )
    assert resp.status_code == 422


def test_variant_review_defaults_to_deterministic_backend():
    resp = client.post(
        "/agent/variant-review",
        json={"chrom": "chr20", "pos": 4699605, "ref": "G", "alt": "A", "run_id": KNOWN_RUN_ID},
    )
    assert resp.status_code == 201
    assert resp.json()["backend_used"] == "deterministic-fallback"


def test_variant_review_falls_back_to_deterministic_when_llm_backend_unconfigured():
    # No AZURE_AI_FOUNDRY_* env vars are set in CI, so AzureFoundryBackend.is_available()
    # is False and the agent should fall back cleanly rather than erroring out.
    resp = client.post(
        "/agent/variant-review",
        json={
            "chrom": "chr20",
            "pos": 4699605,
            "ref": "G",
            "alt": "A",
            "run_id": KNOWN_RUN_ID,
            "backend": "azure_foundry",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["classification"]
    assert body["guardrail_violations"] == []


def test_variant_review_from_fhir_observation():
    resource = {
        "resourceType": "Observation",
        "component": [
            {"code": {"coding": [{"code": "48000-4"}]}, "valueString": "chr20"},
            {"code": {"coding": [{"code": "81254-5"}]}, "valueInteger": 4699605},
            {"code": {"coding": [{"code": "69547-8"}]}, "valueString": "G"},
            {"code": {"coding": [{"code": "69551-0"}]}, "valueString": "A"},
            {"code": {"coding": [{"code": "48018-6"}]}, "valueString": "PRNP"},
        ],
    }
    resp = client.post("/agent/variant-review/fhir", json={"resource": resource, "run_id": KNOWN_RUN_ID})
    assert resp.status_code == 201
    body = resp.json()
    assert body["variant_key"] == "chr20:4699605:G>A"
    assert body["gene"] == "PRNP"


def test_variant_review_from_fhir_observation_rejects_incomplete_resource():
    resp = client.post(
        "/agent/variant-review/fhir",
        json={"resource": {"resourceType": "Observation", "component": []}, "run_id": KNOWN_RUN_ID},
    )
    assert resp.status_code == 422


def test_variant_review_unknown_run_id_is_still_interpreted():
    # The interpreter itself doesn't require run_id to already exist — only
    # signing off does (via /runs/{run_id}/review-decisions, which 404s for
    # an unknown run). This keeps the two concerns decoupled.
    resp = client.post(
        "/agent/variant-review",
        json={"chrom": "chr20", "pos": 4699605, "ref": "G", "alt": "A", "run_id": "does-not-exist"},
    )
    assert resp.status_code == 201

    signoff_resp = client.post(
        "/runs/does-not-exist/review-decisions",
        json={"variant_key": "chr20:4699605:G>A", "classification": "VUS", "decision": "approved", "reviewer": "j.smith"},
    )
    assert signoff_resp.status_code == 404


# ═══ Advice-scrub on the trace (ADR-0008) ════════════════════════════════════
#
# The scrub used to be applied only to the final summary, so on a live LLM
# backend the model's own reasoning — rendered verbatim in the UI's trace
# panel — could carry treatment language straight to a clinician. These cover
# the fix in api.routers.agent._scrubbed_trace_steps.


def test_model_authored_trace_steps_are_scrubbed_and_reported():
    from api.routers.agent import _scrubbed_trace_steps

    class _Step:
        def __init__(self, type_, content):
            self._d = {"type": type_, "content": content, "timestamp": 0.0}

        def to_dict(self):
            return dict(self._d)

    steps, violations = _scrubbed_trace_steps([
        _Step("thought", "We recommend therapy with the standard medication."),
        _Step("answer", "The patient should start treatment with X."),
    ])

    rendered = " ".join(s.content for s in steps)
    for banned in ("We recommend", "therapy", "medication", "should start"):
        assert banned not in rendered, f"{banned!r} survived the trace scrub"
    assert "[REVIEW REQUIRED]" in rendered
    # A scrub must be surfaced to the reviewer, not applied silently.
    assert violations, "scrubbed trace text produced no guardrail violation"
    assert all(v.startswith("Trace step (") for v in violations)


def test_tool_steps_are_not_scrubbed():
    """`observation` content is curated knowledge-base output, not model prose.

    Scrubbing it would corrupt the audit trail, so it must pass through even
    when it legitimately contains a word like "therapy".
    """
    from api.routers.agent import _scrubbed_trace_steps

    class _Step:
        def to_dict(self):
            return {
                "type": "observation",
                "content": "GeneReviews entry mentions gene therapy trials.",
                "timestamp": 0.0,
            }

    steps, violations = _scrubbed_trace_steps([_Step()])
    assert steps[0].content == "GeneReviews entry mentions gene therapy trials."
    assert violations == []


# ═══ LLM observability (AI-8) ═════════════════════════════════════════════════


def _with_fresh_repo():
    from api.dependencies import get_repository
    from api.repository import FixtureRepository

    repo = FixtureRepository()
    app.dependency_overrides[get_repository] = lambda: repo
    return repo, get_repository


def test_variant_review_reports_llm_usage_and_persists_metrics_row():
    repo, dep = _with_fresh_repo()
    try:
        resp = client.post(
            "/agent/variant-review",
            json={"chrom": "chr20", "pos": 4699605, "ref": "G", "alt": "A", "gene": "PRNP", "run_id": KNOWN_RUN_ID},
        )
    finally:
        app.dependency_overrides.pop(dep, None)
    assert resp.status_code == 201
    body = resp.json()
    # Deterministic default: no LLM is called, so zero calls — truthfully.
    assert body["llm_usage"]["n_llm_calls"] == 0
    assert body["llm_calls"] == []
    assert len(repo._agent_call_metrics) == 1
    row = repo._agent_call_metrics[0]
    assert row["run_id"] == KNOWN_RUN_ID
    assert row["n_llm_calls"] == 0
    assert row["price_table_version"].startswith("list-prices-")
    assert "4699605" not in str(row)


def test_llm_calls_survive_deterministic_fallback(monkeypatch):
    # openai with no key: the agent's LLM call fails, the route falls back to
    # the deterministic interpreter — the failed call must still be accounted.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    repo, dep = _with_fresh_repo()
    try:
        resp = client.post(
            "/agent/variant-review",
            json={"chrom": "chr20", "pos": 4699605, "ref": "G", "alt": "A", "run_id": KNOWN_RUN_ID, "backend": "openai"},
        )
    finally:
        app.dependency_overrides.pop(dep, None)
    assert resp.status_code == 201
    body = resp.json()
    assert body["llm_usage"]["n_llm_calls"] == 1
    assert body["llm_usage"]["n_failed_calls"] == 1
    assert body["llm_calls"][0]["prompt_tokens"] is None
    assert body["llm_calls"][0]["estimated_cost_usd"] is None
    row = repo._agent_call_metrics[0]
    assert row["backend"] == "openai"
    assert row["fallback_triggered"] is True
    assert row["prompt_tokens"] is None  # never zero-filled


def test_metrics_write_failure_does_not_fail_interpretation():
    from api.dependencies import get_repository

    class _Broken:
        def record_agent_call_metrics(self, row):
            raise RuntimeError("db down")

    app.dependency_overrides[get_repository] = lambda: _Broken()
    try:
        resp = client.post(
            "/agent/variant-review",
            json={"chrom": "chr20", "pos": 4699605, "ref": "G", "alt": "A", "run_id": KNOWN_RUN_ID},
        )
    finally:
        app.dependency_overrides.pop(get_repository, None)
    assert resp.status_code == 201
