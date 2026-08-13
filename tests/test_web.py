"""Web API tests — the FastAPI layer must mirror the CLI exactly."""

from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(
    loaded_db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    monkeypatch.setenv("NDCRES_DB", str(loaded_db_path))
    from ndcres.web.app import app

    return TestClient(app)


class TestResolveEndpoint:
    def test_anchor_resolves_with_corrected_tiers(self, client: TestClient) -> None:
        response = client.get("/api/resolve/0378-4642-26")
        assert response.status_code == 200
        payload = response.json()
        tier1 = {entry["ndc11"] for entry in payload["tiers"]["T1"]}
        assert "65162099308" in tier1  # Dotti
        tier3 = {entry["ndc11"] for entry in payload["tiers"]["T3"]}
        assert "65162014908" in tier3  # Lyllana
        assert payload["disclaimer"]

    def test_unknown_ndc_is_404_with_detail(self, client: TestClient) -> None:
        response = client.get("/api/resolve/9999-9999-99")
        assert response.status_code == 404
        assert "unknown" in response.json()["detail"]

    def test_web_json_matches_cli_json(
        self, client: TestClient, loaded_conn  # type: ignore[no-untyped-def]
    ) -> None:
        from ndcres.resolve import resolve
        from ndcres.serialize import resolution_dict

        via_web = client.get("/api/resolve/0378-4642-26").json()
        via_cli = resolution_dict(resolve(loaded_conn, "0378-4642-26"))
        assert via_web == via_cli  # one serializer, zero drift


class TestExplainEndpoint:
    def test_lyllana_verdict(self, client: TestClient) -> None:
        response = client.get("/api/explain/00378-4642-26/65162-149-08")
        assert response.status_code == 200
        payload = response.json()
        assert payload["verdict"] == "T3"
        assert payload["reasons"][0]["code"] == "different-te-subgroup"
        assert "three-character code" in payload["reasons"][0]["language"]


class TestSignalEndpoint:
    def test_signal_components(self, client: TestClient) -> None:
        response = client.get("/api/signal/70710119308")
        assert response.status_code == 200
        payload = response.json()
        dropout = next(
            c for c in payload["components"] if c["name"] == "survey-dropout"
        )
        assert dropout["fired"] is True
        assert payload["note"].startswith("The score is a documented heuristic")


class TestSearchEndpoint:
    def test_search_by_brand(self, client: TestClient) -> None:
        response = client.get("/api/search", params={"q": "dotti"})
        assert response.status_code == 200
        results = response.json()["results"]
        assert any(r["ndc11"] == "65162099308" for r in results)

    def test_search_by_ndc_fragment(self, client: TestClient) -> None:
        response = client.get("/api/search", params={"q": "0378-4642"})
        results = response.json()["results"]
        assert any(r["ndc11"] == "00378464226" for r in results)


class TestMetaEndpoint:
    def test_vintages_reported(self, client: TestClient) -> None:
        payload = client.get("/api/meta").json()
        sources = {entry["source"] for entry in payload["sources"]}
        assert {"ndc", "orangebook", "rxnorm", "nadac", "shortage", "link"} <= sources
