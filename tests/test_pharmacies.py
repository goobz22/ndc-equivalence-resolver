"""Pharmacy locator (SPEC §14, §17): injected fetcher, zero network.

Every branch exercised with a fake registry: retail-first ordering,
LOCATION-over-MAILING, the single widen, and the honest failure modes.
A live NPI smoke exists behind NDCRES_LIVE=1 only.
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ndcres.web.pharmacies import UpstreamError, find_pharmacies


def _record(
    name: str,
    kind_code: str = "3336C0003X",
    purpose: str = "LOCATION",
    phone: str | None = "555-0100",
) -> dict[str, Any]:
    return {
        "basic": {"organization_name": name},
        "taxonomies": [{"code": kind_code}],
        "addresses": [
            {
                "address_purpose": "MAILING",
                "address_1": "PO BOX 1 (corporate)",
                "city": "ELSEWHERE",
                "state": "XX",
                "postal_code": "000000000",
            },
            {
                "address_purpose": purpose,
                "address_1": "1 MAIN ST",
                "city": "TOWNSVILLE",
                "state": "TX",
                "postal_code": "750010000",
                "telephone_number": phone,
            },
        ],
    }


class TestFindPharmacies:
    def test_retail_sorts_first(self) -> None:
        results = {
            "results": [
                _record("ZETA MAIL", kind_code="3336M0002X"),
                _record("ALPHA SPECIALTY", kind_code="3336S0011X"),
                _record("OMEGA RETAIL", kind_code="3336C0003X"),
            ]
        }
        payload = find_pharmacies("75001", fetch=lambda url: results)
        kinds = [entry["kind"] for entry in payload["pharmacies"]]
        assert kinds == ["retail", "specialty", "mail-order"]
        assert payload["pharmacies"][0]["name"] == "OMEGA RETAIL"

    def test_location_address_only_never_mailing(self) -> None:
        payload = find_pharmacies(
            "75001", fetch=lambda url: {"results": [_record("A")]}
        )
        entry = payload["pharmacies"][0]
        assert entry["address"] == "1 MAIN ST"
        assert entry["zip"] == "75001"
        assert entry["phone"] == "555-0100"

    def test_record_without_location_address_is_dropped(self) -> None:
        # A mailing-only registration routes to corporate — useless for
        # "get it filled near you"; dropping beats misdirecting.
        record = _record("MAILONLY")
        record["addresses"] = [record["addresses"][0]]
        payload = find_pharmacies(
            "75001", fetch=lambda url: {"results": [record]}
        )
        assert payload["pharmacies"] == []

    def test_zero_results_widens_exactly_once(self) -> None:
        calls: list[str] = []

        def fetch(url: str) -> dict[str, Any]:
            calls.append(url)
            if "750*" in url:
                return {"results": [_record("WIDER")]}
            return {"results": []}

        payload = find_pharmacies("75001", fetch=fetch)
        assert payload["widened"] is True
        assert len(calls) == 2
        assert "postal_code=75001" in calls[0]
        assert "postal_code=750%2A" in calls[1]
        assert payload["pharmacies"][0]["name"] == "WIDER"

    def test_upstream_error_propagates(self) -> None:
        def fetch(url: str) -> dict[str, Any]:
            raise UpstreamError("down")

        with pytest.raises(UpstreamError):
            find_pharmacies("75001", fetch=fetch)

    def test_payload_carries_attribution_and_honesty(self) -> None:
        payload = find_pharmacies("75001", fetch=lambda url: {"results": []})
        assert "72 FR 30011" in payload["attribution"]
        assert "not a statement" in payload["note"]


class TestEndpoints:
    @pytest.fixture()
    def client(self) -> TestClient:
        from ndcres.web.app import app

        return TestClient(app)

    def test_invalid_zip_422(self, client: TestClient) -> None:
        assert client.get("/api/pharmacies?zip=abcde").status_code == 422
        assert client.get("/api/pharmacies?zip=1234").status_code == 422
        assert client.get("/api/pharmacies").status_code == 422

    def test_upstream_failure_503_with_retry_after(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ndcres.web.pharmacies as pharmacies_module

        def broken(url: str) -> dict[str, Any]:
            raise UpstreamError("registry down")

        monkeypatch.setattr(pharmacies_module, "_default_fetcher", broken)
        response = client.get("/api/pharmacies?zip=75001")
        assert response.status_code == 503
        assert response.headers["retry-after"] == "60"

    def test_success_carries_day_cache(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ndcres.web.pharmacies as pharmacies_module

        monkeypatch.setattr(
            pharmacies_module,
            "_default_fetcher",
            lambda url: {"results": [_record("CACHED RX")]},
        )
        response = client.get("/api/pharmacies?zip=75001")
        assert response.status_code == 200
        assert "max-age=86400" in response.headers["cache-control"]
        assert response.json()["pharmacies"][0]["name"] == "CACHED RX"

    def test_costplus_disabled_404s(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("NDCRES_COSTPLUS", raising=False)
        response = client.get("/api/costplus/00378464226")
        assert response.status_code == 404
        assert "not enabled" in response.json()["detail"]

    def test_costplus_enabled_serves_via_fetcher(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ndcres.web.costplus as costplus_module

        monkeypatch.setenv("NDCRES_COSTPLUS", "1")
        monkeypatch.setattr(
            costplus_module,
            "_default_fetcher",
            lambda url: {
                "results": [
                    {
                        "medication_name": "Example 10mg",
                        "quantity": 30,
                        "unit_price": 0.12,
                        "requires_membership": False,
                        "url": "https://costplusdrugs.com/medications/x",
                    }
                ]
            },
        )
        response = client.get("/api/costplus/0378-4642-26")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ndc11"] == "00378464226"
        assert payload["matches"][0]["unit_price"] == 0.12
        assert "stock claim" in payload["disclaimer"]

    def test_meta_features_truthful(
        self, monkeypatch: pytest.MonkeyPatch, loaded_db_path: Any
    ) -> None:
        # T11 discipline in reverse: never advertise what is off.
        monkeypatch.setenv("NDCRES_DB", str(loaded_db_path))
        monkeypatch.delenv("NDCRES_COSTPLUS", raising=False)
        from ndcres.web.app import app

        features = TestClient(app).get("/api/meta").json()["features"]
        assert features == {"pharmacy_locator": True, "costplus": False}
        monkeypatch.setenv("NDCRES_COSTPLUS", "1")
        features = TestClient(app).get("/api/meta").json()["features"]
        assert features["costplus"] is True


@pytest.mark.skipif(
    os.environ.get("NDCRES_LIVE") != "1",
    reason="live NPI smoke only with NDCRES_LIVE=1",
)
class TestLiveSmoke:
    def test_real_registry_answers(self) -> None:
        payload = find_pharmacies("75001")
        assert payload["pharmacies"]
