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
