"""Unit tests for dashboards/metabase/provision_metabase.py.

These mock the Metabase REST API entirely (no live Metabase needed) and
verify MetabaseClient's idempotent get-or-create behavior and the request
payloads it sends — the same dependency-free style as
tests/test_build_metrics.py.
"""
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]


def _load(module_path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


provision_metabase = _load(
    ROOT / "dashboards" / "metabase" / "provision_metabase.py", "provision_metabase"
)
MetabaseClient = provision_metabase.MetabaseClient


def _client_with_mock_session():
    session = MagicMock()
    client = MetabaseClient("http://mb.test", session=session)
    return client, session


def _json_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_authenticate_sets_session_header():
    client, session = _client_with_mock_session()
    session.post.return_value = _json_response({"id": "tok-123"})

    client.authenticate("admin@example.com", "hunter2")

    session.post.assert_called_once_with(
        "http://mb.test/api/session",
        json={"username": "admin@example.com", "password": "hunter2"},
        timeout=10,
    )
    session.headers.update.assert_called_once_with({"X-Metabase-Session": "tok-123"})


def test_get_or_create_database_returns_existing_without_posting():
    client, session = _client_with_mock_session()
    session.get.return_value = _json_response([{"id": 7, "name": "cgp"}])

    result = client.get_or_create_database("cgp", "postgres", {})

    assert result == {"id": 7, "name": "cgp"}
    session.post.assert_not_called()


def test_get_or_create_database_creates_when_missing():
    client, session = _client_with_mock_session()
    session.get.return_value = _json_response([])
    session.post.return_value = _json_response({"id": 9, "name": "cgp"})

    result = client.get_or_create_database("cgp", "postgres", {"host": "postgres"})

    assert result == {"id": 9, "name": "cgp"}
    session.post.assert_called_once_with(
        "http://mb.test/api/database",
        json={"name": "cgp", "engine": "postgres", "details": {"host": "postgres"}},
        timeout=10,
    )


def test_get_or_create_card_is_idempotent_by_name():
    client, session = _client_with_mock_session()
    session.get.return_value = _json_response(
        {"data": [{"id": 3, "name": "Validation pass rate"}]}
    )

    result = client.get_or_create_card(
        "Validation pass rate", "SELECT 1;", "scalar", database_id=1, collection_id=2
    )

    assert result["id"] == 3
    session.post.assert_not_called()


def test_add_cards_to_dashboard_sends_bulk_payload():
    client, session = _client_with_mock_session()
    session.put.return_value = _json_response({})

    cards = [{"id": -1, "card_id": 20, "row": 8, "col": 0, "size_x": 12, "size_y": 4}]
    client.add_cards_to_dashboard(dashboard_id=10, cards=cards)

    session.put.assert_called_once_with(
        "http://mb.test/api/dashboard/10/cards",
        json={"cards": cards},
        timeout=10,
    )


def test_template_tags_for_extracts_each_distinct_variable():
    sql = (
        "SELECT * FROM fact_run WHERE 1=1 "
        "[[AND sample_id = {{sample_id}}]] [[AND caller = {{caller}}]] "
        "[[AND caller = {{ caller }}]]"
    )

    tags = provision_metabase.template_tags_for(sql)

    assert set(tags) == {"sample_id", "caller"}
    assert tags["sample_id"]["type"] == "text"
    assert tags["sample_id"]["name"] == "sample_id"
    assert tags["sample_id"]["display-name"] == "Sample Id"


def test_template_tags_for_empty_when_no_variables():
    assert provision_metabase.template_tags_for("SELECT 1;") == {}


def test_get_or_create_card_includes_template_tags_when_creating():
    client, session = _client_with_mock_session()
    session.get.return_value = _json_response([])
    session.post.return_value = _json_response({"id": 5})

    client.get_or_create_card(
        "Self-service cohort explorer",
        "SELECT * FROM fact_run WHERE 1=1 [[AND sample_id = {{sample_id}}]]",
        "table",
        database_id=1,
        collection_id=2,
    )

    posted = session.post.call_args.kwargs["json"]
    assert "sample_id" in posted["dataset_query"]["native"]["template-tags"]


def test_provision_gives_each_new_dashcard_a_unique_negative_id():
    """Regression test: Metabase's bulk PUT /api/dashboard/:id/cards rejects
    the whole batch with "ids are unique" if two new cards share the same
    placeholder id — caught by running provision_metabase.py against a real
    Metabase instance, not by the mocked tests above."""
    client = MagicMock()
    client.get_or_create_database.return_value = {"id": 2}
    client.get_or_create_collection.return_value = {"id": 5}
    client.get_or_create_dashboard.return_value = {"id": 10}
    client.get_or_create_card.side_effect = [{"id": 100}, {"id": 101}, {"id": 102}]

    manifest = {
        "database": {"name": "cgp", "engine": "postgres", "details": {}},
        "collections": [
            {
                "name": "Clinical Genomics Ops",
                "dashboard": "Clinical Genomics Ops",
                "cards": [
                    {"name": "Card A", "sql": "SELECT 1;", "display": "scalar"},
                    {"name": "Card B", "sql": "SELECT 2;", "display": "scalar"},
                    {"name": "Card C", "sql": "SELECT 3;", "display": "scalar"},
                ],
            }
        ],
    }

    provision_metabase.provision(client, manifest)

    client.add_cards_to_dashboard.assert_called_once()
    dashcards = client.add_cards_to_dashboard.call_args.args[1]
    ids = [c["id"] for c in dashcards]
    assert len(ids) == len(set(ids)), f"dashcard ids must be unique, got {ids}"
    assert all(i < 0 for i in ids), "new dashcards must use negative placeholder ids"


def test_manifest_loads_and_matches_expected_shape():
    manifest = provision_metabase.load_manifest(provision_metabase.DEFAULT_MANIFEST)

    assert manifest["database"]["engine"] == "postgres"
    collection_names = {c["name"] for c in manifest["collections"]}
    assert collection_names == {"CGP Ops", "CGP Analytics"}
    total_cards = sum(len(c["cards"]) for c in manifest["collections"])
    assert total_cards == 10
