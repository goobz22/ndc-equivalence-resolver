"""Web API tests — the FastAPI layer must mirror the CLI exactly."""

import sqlite3
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
        self, client: TestClient, loaded_conn: sqlite3.Connection
    ) -> None:
        from ndcres.provenance import source_refs
        from ndcres.resolve import resolve
        from ndcres.serialize import resolution_dict

        via_web = client.get("/api/resolve/0378-4642-26").json()
        via_cli = resolution_dict(
            resolve(loaded_conn, "0378-4642-26"),
            sources=source_refs(loaded_conn),
        )
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


class TestClassEndpoints:
    @pytest.fixture()
    def swept_client(
        self, loaded_db_path: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> TestClient:
        import shutil

        from ndcres.db import connect
        from ndcres.sweep import persist_sweep, run_sweep

        db_copy = tmp_path / "swept.db"
        shutil.copy(loaded_db_path, db_copy)
        conn = connect(db_copy)
        persist_sweep(conn, run_sweep(conn))
        conn.close()
        monkeypatch.setenv("NDCRES_DB", str(db_copy))
        from ndcres.web.app import app

        return TestClient(app)

    def test_class_endpoint_resolves_by_slug(
        self, swept_client: TestClient
    ) -> None:
        from ndcres.classpage import class_slug

        slug = class_slug("ESTRADIOL", "SYSTEM;TRANSDERMAL", "UG24H:50", "AB1")
        payload = swept_client.get(f"/api/class/{slug}").json()
        assert payload["class"]["rep_ndc11"] == "00378464226"
        tier1 = {
            entry["ndc11"] for entry in payload["resolution"]["tiers"]["T1"]
        }
        assert "65162099308" in tier1  # Dotti — the anchor golden holds

    def test_unknown_slug_404s_helpfully(
        self, swept_client: TestClient
    ) -> None:
        response = swept_client.get("/api/class/nonsense-00000000")
        assert response.status_code == 404
        assert "latest sweep" in response.json()["detail"]

    def test_classes_index_covers_every_class(
        self, swept_client: TestClient
    ) -> None:
        payload = swept_client.get("/api/classes").json()
        assert payload["count"] == len(payload["classes"]) > 0
        slugs = [entry["slug"] for entry in payload["classes"]]
        assert len(slugs) == len(set(slugs))

    def test_gaps_feed_serves_parseable_rss(
        self, swept_client: TestClient
    ) -> None:
        import xml.etree.ElementTree as ET

        response = swept_client.get("/api/feeds/gaps.xml")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "application/rss+xml"
        )
        assert "max-age=3600" in response.headers["cache-control"]
        parsed = ET.fromstring(response.content)
        assert parsed.tag == "rss"

    def test_class_feed_404s_on_unknown_slug(
        self, swept_client: TestClient
    ) -> None:
        response = swept_client.get("/api/feeds/class/nonsense-00000000.xml")
        assert response.status_code == 404

    def test_class_feed_serves_current_state(
        self, swept_client: TestClient
    ) -> None:
        import xml.etree.ElementTree as ET

        from ndcres.classpage import class_slug

        slug = class_slug("ESTRADIOL", "SYSTEM;TRANSDERMAL", "UG24H:50", "AB1")
        response = swept_client.get(f"/api/feeds/class/{slug}.xml")
        assert response.status_code == 200
        parsed = ET.fromstring(response.content)
        items = parsed.findall("channel/item")
        assert len(items) >= 1
        guid = items[0].find("guid")
        assert guid is not None and guid.text is not None
        assert guid.text.endswith(":current")

    def test_resolution_carries_class_ref(
        self, swept_client: TestClient
    ) -> None:
        from ndcres.classpage import class_slug

        payload = swept_client.get("/api/resolve/0378-4642-26").json()
        ref = payload["class_ref"]
        assert ref is not None
        assert ref["slug"] == class_slug(
            "ESTRADIOL", "SYSTEM;TRANSDERMAL", "UG24H:50", "AB1"
        )


class TestMetaEndpoint:
    def test_vintages_reported(self, client: TestClient) -> None:
        payload = client.get("/api/meta").json()
        sources = {entry["source"] for entry in payload["sources"]}
        assert {"ndc", "orangebook", "rxnorm", "nadac", "shortage", "link"} <= sources
