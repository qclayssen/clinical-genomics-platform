"""Tests for the FastAPI service — runs entirely against the fixture backend."""

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_healthz():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_runs():
    resp = client.get("/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 3
    assert {r["run_id"] for r in body} == {"run_2026_0301_a", "run_2026_0308_b", "run_2026_0315_c"}


def test_list_runs_filters_by_caller():
    resp = client.get("/runs", params={"caller": "deepvariant"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["run_id"] == "run_2026_0315_c"


def test_list_runs_filters_by_validation_pass():
    resp = client.get("/runs", params={"validation_pass": False})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["run_id"] == "run_2026_0315_c"


def test_get_run():
    resp = client.get("/runs/run_2026_0301_a")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sample_id"] == "HG002_chr20"
    assert body["qc"]["snp_f1"] == 0.9978


def test_get_run_not_found():
    resp = client.get("/runs/does-not-exist")
    assert resp.status_code == 404


def test_get_provenance():
    resp = client.get("/runs/run_2026_0301_a/provenance")
    assert resp.status_code == 200
    body = resp.json()
    assert body["git_commit"] == "abc1234"
    assert body["truth_version"] == "GIAB-v4.2.1"
    assert "HG002_chr20.markdup.metrics" in body["input_checksums"]


def test_provenance_not_found():
    resp = client.get("/runs/does-not-exist/provenance")
    assert resp.status_code == 404


def test_list_qc_warnings():
    resp = client.get("/runs/run_2026_0308_b/qc-warnings")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["overall_status"] == "warn"
    assert body[0]["metric_name"] == "percent_duplication"


def test_qc_warnings_empty_for_clean_run():
    resp = client.get("/runs/run_2026_0301_a/qc-warnings")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_review_decision():
    payload = {
        "variant_key": "chr20:1234567:A>G",
        "classification": "likely_pathogenic",
        "decision": "approved",
        "reviewer": "test-reviewer",
        "comment": "Looks right.",
    }
    resp = client.post("/runs/run_2026_0301_a/review-decisions", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["run_id"] == "run_2026_0301_a"
    assert body["decision"] == "approved"
    assert "id" in body and "decided_at" in body


def test_create_review_decision_invalid_decision_value():
    payload = {
        "variant_key": "chr20:1234567:A>G",
        "classification": "likely_pathogenic",
        "decision": "maybe",
        "reviewer": "test-reviewer",
    }
    resp = client.post("/runs/run_2026_0301_a/review-decisions", json=payload)
    assert resp.status_code == 422


def test_create_review_decision_run_not_found():
    payload = {
        "variant_key": "chr20:1234567:A>G",
        "classification": "likely_pathogenic",
        "decision": "approved",
        "reviewer": "test-reviewer",
    }
    resp = client.post("/runs/does-not-exist/review-decisions", json=payload)
    assert resp.status_code == 404


def test_openapi_schema_is_served():
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["info"]["title"] == "Clinical Genomics Insight Platform API"
    assert "/runs/{run_id}/review-decisions" in schema["paths"]
