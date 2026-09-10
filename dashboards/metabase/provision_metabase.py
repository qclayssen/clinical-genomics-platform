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
import re
import uuid
from pathlib import Path
from typing import Any

import requests
import yaml

DEFAULT_MANIFEST = Path(__file__).with_name("dashboard_manifest.yaml")

_TEMPLATE_TAG_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def template_tags_for(sql: str) -> dict[str, Any]:
    """Build the native-query template-tags Metabase requires for every {{tag}}.

    Metabase's card-creation API rejects (or silently can't run) a native
    query containing `{{tag}}` unless `dataset_query.native.template-tags`
    describes each tag — the frontend normally computes this, but nothing
    does it automatically when a card is created via the API directly. This
    declares each tag as a plain text Variable, not a Field Filter: a real
    Field Filter needs the target column's live Metabase field ID, which is
    only known after Metabase finishes syncing the database's schema — a
    round trip this script doesn't perform. See ADR-0024.
    """
    tags: dict[str, Any] = {}
    for tag_name in _TEMPLATE_TAG_RE.findall(sql):
        if tag_name in tags:
            continue
        tags[tag_name] = {
            "id": str(uuid.uuid4()),
            "name": tag_name,
            "display-name": tag_name.replace("_", " ").title(),
            "type": "text",
        }
    return tags


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
        self,
        name: str,
        sql: str,
        display: str,
        database_id: int,
        collection_id: int,
        graph_dimensions: list[str] | None = None,
        graph_metrics: list[str] | None = None,
    ) -> dict[str, Any]:
        existing = self._find_by_name("/api/card", name)
        if existing:
            return existing

        # Line/bar cards with more than one non-metric column (e.g. grouped
        # by two dimensions) render as an unhelpful "Which fields do you
        # want to use for the X and Y axes?" prompt until someone picks
        # axes by hand — Metabase can't always infer them. Manifest entries
        # can set graph_dimensions/graph_metrics to pre-select them so the
        # card renders immediately, no manual step needed.
        viz_settings: dict[str, Any] = {}
        if graph_dimensions:
            viz_settings["graph.dimensions"] = graph_dimensions
        if graph_metrics:
            viz_settings["graph.metrics"] = graph_metrics

        resp = self.session.post(
            f"{self.base_url}/api/card",
            json={
                "name": name,
                "display": display,
                "collection_id": collection_id,
                "visualization_settings": viz_settings,
                "dataset_query": {
                    "type": "native",
                    "native": {"query": sql, "template-tags": template_tags_for(sql)},
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

    def add_cards_to_dashboard(self, dashboard_id: int, cards: list[dict[str, Any]]) -> None:
        """Replace a dashboard's card layout in one call.

        Metabase removed the old per-card `POST /api/dashboard/:id/cards` in
        favor of a bulk `PUT` that takes the full desired card list — so this
        is called once per dashboard with every card, not once per card. New
        cards use a unique negative id (Metabase's marker for "not yet a
        dashcard" — every new card in the same call needs a *distinct*
        negative id, or the API rejects the whole batch with
        "ids are unique").
        """
        resp = self.session.put(
            f"{self.base_url}/api/dashboard/{dashboard_id}/cards",
            json={"cards": cards},
            timeout=10,
        )
        resp.raise_for_status()

    def enable_signed_embedding(self, dashboard_id: int) -> None:
        # Per-dashboard embedding is rejected with "Embedding is not
        # enabled." until the instance-wide setting is on — a fresh
        # Metabase install has it off by default.
        instance_resp = self.session.put(
            f"{self.base_url}/api/setting/enable-embedding",
            json={"value": True},
            timeout=10,
        )
        instance_resp.raise_for_status()

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

        dashcards = []
        for row, card_spec in enumerate(collection_spec["cards"]):
            card = client.get_or_create_card(
                card_spec["name"],
                card_spec["sql"],
                card_spec["display"],
                database["id"],
                collection["id"],
                graph_dimensions=card_spec.get("graph_dimensions"),
                graph_metrics=card_spec.get("graph_metrics"),
            )
            dashcards.append(
                {"id": -(row + 1), "card_id": card["id"], "row": row * 4, "col": 0, "size_x": 12, "size_y": 4}
            )
        client.add_cards_to_dashboard(dashboard["id"], dashcards)

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
