"""CORS for the deployed frontend (azure/README.md builds web/ with
VITE_API_BASE_URL pointing straight at the API host, so the browser makes
cross-origin calls). Off by default; opt in via CGP_CORS_ORIGINS."""
import importlib

from fastapi.testclient import TestClient

import api.main


def _client(monkeypatch, origins: str | None) -> TestClient:
    if origins is None:
        monkeypatch.delenv("CGP_CORS_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("CGP_CORS_ORIGINS", origins)
    return TestClient(importlib.reload(api.main).app)


def _preflight(client: TestClient, origin: str):
    return client.options(
        "/agent/variant-review",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )


def test_no_cors_headers_by_default(monkeypatch):
    resp = _client(monkeypatch, None).get("/healthz", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in resp.headers


def test_configured_origin_is_allowed(monkeypatch):
    client = _client(monkeypatch, "https://cgp-web.azurestaticapps.net, http://localhost:5173")
    resp = _preflight(client, "https://cgp-web.azurestaticapps.net")
    assert resp.headers["access-control-allow-origin"] == "https://cgp-web.azurestaticapps.net"


def test_unlisted_origin_is_not_allowed(monkeypatch):
    client = _client(monkeypatch, "https://cgp-web.azurestaticapps.net")
    resp = _preflight(client, "https://evil.example")
    assert resp.headers.get("access-control-allow-origin") != "https://evil.example"


def teardown_module(module):
    import os
    os.environ.pop("CGP_CORS_ORIGINS", None)
    importlib.reload(api.main)
