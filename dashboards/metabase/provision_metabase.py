"""Provision the Clinical Genomics Ops Metabase dashboard via the REST API.

Reads dashboard_manifest.yaml (the single source of truth for cards/SQL)
and idempotently creates the matching database connection, collections,
native-question cards, and dashboards in a running Metabase instance —
the infrastructure-as-code alternative to clicking a dashboard together
by hand and hoping someone remembers to export it.

Needs environment: a running Metabase instance (docker compose up, see
README.md in this directory) and MB_USERNAME/MB_PASSWORD env vars for an
existing Metabase admin account. Not run in CI — see ADR-0024.

Usage:
    MB_USERNAME=admin@example.com MB_PASSWORD=... python provision_metabase.py
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests
import yaml

DEFAULT_MANIFEST = Path(__file__).with_name("dashboard_manifest.yaml")


class MetabaseClient:
    """Thin wrapper around the subset of the Metabase REST API this script needs."""

    def __init__(self, base_url: str, session: requests.Session | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()

    def authenticate(self, username: str, password: str) -> None:
        resp = self.session.post(
            f"{self.base_url}/api/session",
            json={"username": username, "password": password},
            timeout=10,
        )
        resp.raise_for_status()
        self.session.headers.update({"X-Metabase-Session": resp.json()["id"]})

    def _list(self, path: str) -> list[dict[str, Any]]:
        resp = self.session.get(f"{self.base_url}{path}", timeout=10)
        resp.raise_for_status()
        body = resp.json()
        return body["data"] if isinstance(body, dict) and "data" in body else body

    def _find_by_name(self, path: str, name: str) -> dict[str, Any] | None:
        for item in self._list(path):
            if item.get("name") == name:
                return item
        return None

    def get_or_create_database(self, name: str, engine: str, details: dict[str, Any]) -> dict[str, Any]:
        existing = self._find_by_name("/api/database", name)
        if existing:
            return existing
        resp = self.session.post(
            f"{self.base_url}/api/database",
            json={"name": name, "engine": engine, "details": details},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_or_create_collection(self, name: str) -> dict[str, Any]:
        existing = self._find_by_name("/api/collection", name)
        if existing:
            return existing
        resp = self.session.post(
            f"{self.base_url}/api/collection",
            json={"name": name, "color": "#509EE3"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_or_create_card(
        self, name: str, sql: str, display: str, database_id: int, collection_id: int
    ) -> dict[str, Any]:
        existing = self._find_by_name("/api/card", name)
        if existing:
            return existing
        resp = self.session.post(
            f"{self.base_url}/api/card",
            json={
                "name": name,
                "display": display,
                "collection_id": collection_id,
                "visualization_settings": {},
                "dataset_query": {
                    "type": "native",
                    "native": {"query": sql},
                    "database": database_id,
                },
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_or_create_dashboard(self, name: str, collection_id: int) -> dict[str, Any]:
        existing = self._find_by_name("/api/dashboard", name)
        if existing:
            return existing
        resp = self.session.post(
            f"{self.base_url}/api/dashboard",
            json={"name": name, "collection_id": collection_id},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def add_card_to_dashboard(
        self, dashboard_id: int, card_id: int, row: int, col: int = 0, size_x: int = 12, size_y: int = 4
    ) -> None:
        resp = self.session.post(
            f"{self.base_url}/api/dashboard/{dashboard_id}/cards",
            json={"cardId": card_id, "row": row, "col": col, "size_x": size_x, "size_y": size_y},
            timeout=10,
        )
        resp.raise_for_status()

    def enable_signed_embedding(self, dashboard_id: int) -> None:
        resp = self.session.put(
            f"{self.base_url}/api/dashboard/{dashboard_id}",
            json={"enable_embedding": True, "embedding_params": {}},
            timeout=10,
        )
        resp.raise_for_status()


def load_manifest(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f)


def provision(client: MetabaseClient, manifest: dict[str, Any]) -> None:
    db = manifest["database"]
    database = client.get_or_create_database(db["name"], db["engine"], db["details"])

    for collection_spec in manifest["collections"]:
        collection = client.get_or_create_collection(collection_spec["name"])
        dashboard = client.get_or_create_dashboard(collection_spec["dashboard"], collection["id"])

        for row, card_spec in enumerate(collection_spec["cards"]):
            card = client.get_or_create_card(
                card_spec["name"],
                card_spec["sql"],
                card_spec["display"],
                database["id"],
                collection["id"],
            )
            client.add_card_to_dashboard(dashboard["id"], card["id"], row=row * 4)

        if collection_spec.get("embed"):
            client.enable_signed_embedding(dashboard["id"])


def main() -> None:
    base_url = os.environ.get("MB_URL", "http://localhost:3000")
    username = os.environ["MB_USERNAME"]
    password = os.environ["MB_PASSWORD"]
    manifest_path = Path(os.environ.get("MB_MANIFEST", str(DEFAULT_MANIFEST)))

    client = MetabaseClient(base_url)
    client.authenticate(username, password)
    provision(client, load_manifest(manifest_path))
    print("Provisioning complete.")


if __name__ == "__main__":
    main()
