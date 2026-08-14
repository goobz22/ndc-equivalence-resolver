"""Ingest + link-builder tests against the byte-exact fixture slices."""

import sqlite3
from pathlib import Path

from conftest import FULL, NDC_V2

from ndcres.ingest import refresh


class TestNdcDirectoryIngest:
    def test_anchor_product_fields(self, loaded_conn: sqlite3.Connection) -> None:
        row = loaded_conn.execute(
            "SELECT * FROM product WHERE ndc9 = '003784642'"
        ).fetchone()
        assert row["appl_type"] == "A"
        assert row["appl_no"] == "201675"
        assert row["strength_norm"] == "UG24H:50"
        assert row["form_family"] == "patch"
        assert row["ingredient_set"] == "ESTRADIOL"
        assert row["labeler_name"] == "Mylan Pharmaceuticals Inc."
        assert row["end_marketing"] is None

    def test_anchor_package_fields(self, loaded_conn: sqlite3.Connection) -> None:
        row = loaded_conn.execute(
            "SELECT * FROM package WHERE ndc11 = '00378464226'"
        ).fetchone()
        assert row["ndc_shape"] == "4-4-2"
        assert row["pack_count"] == 8
        assert row["wear_hours"] == 84.0
        assert row["package_ndc_filed"] == "0378-4642-26"

    def test_all_three_shapes_ingested(self, loaded_conn: sqlite3.Connection) -> None:
        shapes = {
            row["ndc_shape"]
            for row in loaded_conn.execute("SELECT DISTINCT ndc_shape FROM package")
        }
        assert {"4-4-2", "5-3-2", "5-4-1"} <= shapes

    def test_cp1252_labeler_survives(self, loaded_conn: sqlite3.Connection) -> None:
        row = loaded_conn.execute(
            "SELECT labeler_name FROM product WHERE ndc9 = '435980115'"
        ).fetchone()
        assert row["labeler_name"] == "Dr. Reddy’s Laboratories Inc."

    def test_menostar_special_case_applied(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        row = loaded_conn.execute(
            "SELECT appl_no, appl_no_raw, ob_link_status FROM product "
            "WHERE ndc9 = '504190455'"
        ).fetchone()
        assert row["appl_no"] == "021674"  # corrected
        assert row["appl_no_raw"] == "020375"  # the upstream defect, preserved
        assert row["ob_link_status"] == "special-cased"

    def test_combo_product_ingredient_set(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        row = loaded_conn.execute(
            "SELECT ingredient_set, ingredient_count FROM product "
            "WHERE ndc9 = '504190491'"
        ).fetchone()
        assert row["ingredient_set"] == "ESTRADIOL|LEVONORGESTREL"
        assert row["ingredient_count"] == 2

    def test_otc_monograph_has_no_application(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        row = loaded_conn.execute(
            "SELECT appl_type, ob_link_status FROM product WHERE ndc9 = '435980115'"
        ).fetchone()
        assert row["appl_type"] is None
        assert row["ob_link_status"] == "no-application"

    def test_sample_package_flagged(self, loaded_conn: sqlite3.Connection) -> None:
        row = loaded_conn.execute(
            "SELECT sample_package FROM package WHERE ndc11 = '00574206700'"
        ).fetchone()
        assert row["sample_package"] == 1


class TestOrangeBookIngest:
    def test_anchor_ob_row(self, loaded_conn: sqlite3.Connection) -> None:
        row = loaded_conn.execute(
            "SELECT * FROM ob_product WHERE appl_type='A' AND appl_no='201675' "
            "AND product_no='003'"
        ).fetchone()
        assert row["te_code"] == "AB1"
        assert row["te_class"] == "AB"
        assert row["te_subscript"] == "1"
        assert row["df_route"] == "SYSTEM;TRANSDERMAL"
        assert row["strength_norm"] == "UG24H:50"
        assert row["ob_type"] == "RX"

    def test_lyllana_is_ab3_under_film_heading(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        row = loaded_conn.execute(
            "SELECT te_code, df_route FROM ob_product "
            "WHERE appl_type='A' AND appl_no='211396' AND product_no='003'"
        ).fetchone()
        assert row["te_code"] == "AB3"
        assert row["df_route"] == "FILM, EXTENDED RELEASE;TRANSDERMAL"

    def test_discn_rows_kept_with_null_te(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        row = loaded_conn.execute(
            "SELECT te_code, ob_type FROM ob_product "
            "WHERE appl_type='N' AND appl_no='020655'"  # Alora
        ).fetchone()
        assert row["te_code"] is None
        assert row["ob_type"] == "DISCN"

    def test_fr_suffix_stripped_and_normalized(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        row = loaded_conn.execute(
            "SELECT strength_raw, strength_norm, approval_date FROM ob_product "
            "WHERE appl_type='N' AND appl_no='084499'"
        ).fetchone()
        assert row["strength_raw"] == "0.5MG"
        assert row["strength_norm"] == "UG:500"
        assert row["approval_date"] == "pre-1982"

    def test_combo_ingredient_set(self, loaded_conn: sqlite3.Connection) -> None:
        row = loaded_conn.execute(
            "SELECT ingredient_set FROM ob_product "
            "WHERE appl_type='N' AND appl_no='021258'"
        ).fetchone()
        assert row["ingredient_set"] == "ESTRADIOL|LEVONORGESTREL"


class TestLinkBuilder:
    def test_anchor_links_by_strength(self, loaded_conn: sqlite3.Connection) -> None:
        row = loaded_conn.execute(
            "SELECT l.product_no, l.match_method, p.ob_link_status "
            "FROM product_ob_link l JOIN product p USING (ndc9) "
            "WHERE l.ndc9 = '003784642'"
        ).fetchone()
        assert row["product_no"] == "003"
        assert row["match_method"] == "appl+strength"
        assert row["ob_link_status"] == "linked"

    def test_menostar_links_to_its_true_application(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        row = loaded_conn.execute(
            "SELECT appl_type, appl_no, product_no, match_method "
            "FROM product_ob_link WHERE ndc9 = '504190455'"
        ).fetchone()
        assert (row["appl_type"], row["appl_no"], row["product_no"]) == (
            "N",
            "021674",
            "001",
        )
        assert row["match_method"] == "special-case"

    def test_authorized_generic_shares_brand_row(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        rows = loaded_conn.execute(
            "SELECT ndc9 FROM product_ob_link "
            "WHERE appl_type='N' AND appl_no='020538' AND product_no='006' "
            "ORDER BY ndc9"
        ).fetchall()
        # Vivelle-Dot brand AND the Sandoz authorized generic — many-to-one.
        assert [r["ndc9"] for r in rows] == ["007817144", "667580147"]

    def test_missing_ob_application_recorded(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        row = loaded_conn.execute(
            "SELECT ob_link_status FROM product WHERE ndc9 = '219220015'"
        ).fetchone()
        assert row["ob_link_status"] == "no-ob-row"

    def test_divigel_links_via_concentration_strength(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        row = loaded_conn.execute(
            "SELECT product_no, match_method FROM product_ob_link "
            "WHERE ndc9 = '680250065'"
        ).fetchone()
        assert row["product_no"] == "001"
        assert row["match_method"] == "appl+strength"


class TestRxNormIngest:
    def test_ndc_to_concept(self, loaded_conn: sqlite3.Connection) -> None:
        row = loaded_conn.execute(
            "SELECT c.tty, c.name FROM rx_ndc n JOIN rx_concept c USING (rxcui) "
            "WHERE n.ndc11 = '00378464226'"
        ).fetchone()
        # Unbranded generic maps straight to the SCD — the real asymmetry.
        assert row["tty"] == "SCD"
        assert row["name"].startswith("84 HR")

    def test_branded_generic_maps_to_sbd(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        row = loaded_conn.execute(
            "SELECT c.tty FROM rx_ndc n JOIN rx_concept c USING (rxcui) "
            "WHERE n.ndc11 = '65162014908'"
        ).fetchone()
        assert row["tty"] == "SBD"


class TestNadacIngest:
    def test_anchor_series_present(self, loaded_conn: sqlite3.Connection) -> None:
        rows = loaded_conn.execute(
            "SELECT effective_date, price FROM nadac WHERE ndc11 = '00378464226' "
            "ORDER BY effective_date"
        ).fetchall()
        assert rows[0]["effective_date"] == "2024-12-18"  # from the 2025 file
        assert rows[-1]["effective_date"] == "2026-07-22"
        assert rows[-1]["price"] == 7.97659

    def test_weekly_restatements_collapse(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        row = loaded_conn.execute(
            "SELECT as_of_first, as_of_last FROM nadac "
            "WHERE ndc11 = '00378464226' AND effective_date = '2026-07-22'"
        ).fetchone()
        # Stated in the 07/22 and 08/12 snapshots; merged to one row.
        assert row["as_of_first"] == "2026-07-22"
        assert row["as_of_last"] == "2026-08-12"

    def test_quoted_explanation_code_list(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        row = loaded_conn.execute(
            "SELECT explanation_codes FROM nadac WHERE ndc11 = '70710119308' "
            "ORDER BY effective_date DESC LIMIT 1"
        ).fetchone()
        assert row["explanation_codes"] == "1,5"


class TestShortageIngest:
    def test_native_segmentation_normalized(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        row = loaded_conn.execute(
            "SELECT ndc11 FROM shortage WHERE company_name LIKE 'Hospira%'"
        ).fetchone()
        assert row["ndc11"] == "00409130431"  # 4-4-2 '0409-1304-31'

    def test_upstream_typo_preserved_verbatim(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        row = loaded_conn.execute(
            "SELECT availability FROM shortage WHERE generic_name LIKE 'Amoxicillin%'"
        ).fetchone()
        assert row["availability"] == "Unvailable"  # never repaired

    def test_duplicate_package_ndc_kept_as_two_records(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        rows = loaded_conn.execute(
            "SELECT status FROM shortage WHERE ndc11 = '00071053023' ORDER BY status"
        ).fetchall()
        assert [r["status"] for r in rows] == ["Current", "Resolved"]

    def test_no_estradiol_records_in_real_slice(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        count = loaded_conn.execute(
            "SELECT count(*) AS n FROM shortage WHERE generic_name LIKE '%stradiol%'"
        ).fetchone()["n"]
        assert count == 0


class TestRefreshSemantics:
    @staticmethod
    def _table_digest(conn: sqlite3.Connection, table: str) -> str:
        import hashlib

        cursor = conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2")  # noqa: S608
        digest = hashlib.sha256()
        for row in cursor:
            # run_id (always the trailing column) changes per refresh by
            # design; content equality is what idempotency promises.
            digest.update(repr(tuple(row)[:-1]).encode())
        return digest.hexdigest()

    def test_double_refresh_is_idempotent(self, fresh_conn: sqlite3.Connection) -> None:
        refresh(fresh_conn, from_dir=FULL)
        first = {
            table: self._table_digest(fresh_conn, table)
            for table in ("product", "package", "ob_product", "rx_ndc", "shortage", "nadac")
        }
        first_counts = {
            table: fresh_conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]  # noqa: S608
            for table in first
        }
        refresh(fresh_conn, from_dir=FULL)
        for table, digest in first.items():
            assert self._table_digest(fresh_conn, table) == digest, table
            count = fresh_conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]  # noqa: S608
            assert count == first_counts[table], table

    def test_mutation_fixture_propagates_change_and_removal(
        self, fresh_conn: sqlite3.Connection
    ) -> None:
        refresh(fresh_conn, from_dir=FULL)
        assert (
            fresh_conn.execute(
                "SELECT count(*) AS n FROM product WHERE ndc9 = '005742067'"
            ).fetchone()["n"]
            == 1
        )
        refresh(fresh_conn, sources=("ndc",), from_dir=NDC_V2)
        # Removal propagated (Evamist gone from product AND package)...
        assert (
            fresh_conn.execute(
                "SELECT count(*) AS n FROM product WHERE ndc9 = '005742067'"
            ).fetchone()["n"]
            == 0
        )
        assert (
            fresh_conn.execute(
                "SELECT count(*) AS n FROM package WHERE ndc9 = '005742067'"
            ).fetchone()["n"]
            == 0
        )
        # ...and the modification landed.
        row = fresh_conn.execute(
            "SELECT proprietary_name FROM product WHERE ndc9 = '651620149'"
        ).fetchone()
        assert row["proprietary_name"] == "LYLLANA XR"
        # NADAC history untouched by an ndc-only refresh.
        assert (
            fresh_conn.execute("SELECT count(*) AS n FROM nadac").fetchone()["n"] > 0
        )

    def test_every_row_carries_provenance(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        for table in ("product", "package", "ob_product", "nadac", "shortage"):
            orphan = loaded_conn.execute(
                f"SELECT count(*) AS n FROM {table} t "  # noqa: S608
                "LEFT JOIN source_run r USING (run_id) WHERE r.run_id IS NULL"
            ).fetchone()["n"]
            assert orphan == 0, table


class TestNadacLegacyHeader:
    def test_underscore_vintage_header_accepted(self, tmp_path: Path) -> None:
        # Yearly NADAC files before 2024 spell the columns with
        # underscores; the parser accepts BOTH verified spellings and
        # still refuses anything else.
        from ndcres.db import connect, start_run
        from ndcres.ingest import nadac

        legacy = tmp_path / "nadac_legacy.csv"
        legacy.write_text(
            "NDC Description,NDC,NADAC_Per_Unit,Effective_Date,Pricing_Unit,"
            "Pharmacy_Type_Indicator,OTC,Explanation_Code,"
            "Classification_for_Rate_Setting,"
            "Corresponding_Generic_Drug_NADAC_Per_Unit,"
            "Corresponding_Generic_Drug_Effective_Date,As of Date\n"
            "FENOFIBRATE 54 MG TABLET,68180023109,0.16400,12/23/2020,EA,"
            "C/I,N,1,G,,,01/06/2021\n",
            encoding="utf-8",
        )
        conn = connect(tmp_path / "t.db")
        with conn:
            run_id = start_run(
                conn, source="nadac", source_url="file://test",
                fetched_at="2026-08-13T00:00:00Z",
            )
            count = nadac.ingest(conn, run_id, (legacy,))
        assert count == 1
        row = conn.execute(
            "SELECT price, effective_date FROM nadac WHERE ndc11='68180023109'"
        ).fetchone()
        assert row["effective_date"] == "2020-12-23"

    def test_snake_case_vintage_header_accepted(self, tmp_path: Path) -> None:
        # 2019-2020 yearly files: quoted lowercase snake_case (a third
        # verified spelling of the same columns).
        from ndcres.db import connect, start_run
        from ndcres.ingest import nadac

        legacy = tmp_path / "nadac_snake.csv"
        legacy.write_text(
            '"ndc_description","ndc","nadac_per_unit","effective_date",'
            '"pricing_unit","pharmacy_type_indicator","otc",'
            '"explanation_code","classification_for_rate_setting",'
            '"corresponding_generic_drug_nadac_per_unit",'
            '"corresponding_generic_drug_effective_date","as_of_date"\n'
            '"CICLOPIROX 0.77% GEL","47781053084","0.92528","12/18/2019",'
            '"GM","C/I","N","1, 5, 6","G",,,"01/01/2020"\n',
            encoding="utf-8",
        )
        conn = connect(tmp_path / "t.db")
        with conn:
            run_id = start_run(
                conn, source="nadac", source_url="file://test",
                fetched_at="2026-08-13T00:00:00Z",
            )
            count = nadac.ingest(conn, run_id, (legacy,))
        assert count == 1
        row = conn.execute(
            "SELECT effective_date FROM nadac WHERE ndc11='47781053084'"
        ).fetchone()
        assert row["effective_date"] == "2019-12-18"

    def test_truly_drifted_header_still_refuses(self, tmp_path: Path) -> None:
        from ndcres.db import connect, start_run
        from ndcres.ingest import nadac

        import pytest

        bad = tmp_path / "nadac_bad.csv"
        bad.write_text("Totally,Different,Columns\n1,2,3\n", encoding="utf-8")
        conn = connect(tmp_path / "t.db")
        with conn:
            run_id = start_run(
                conn, source="nadac", source_url="file://test",
                fetched_at="2026-08-13T00:00:00Z",
            )
            with pytest.raises(ValueError, match="header drifted"):
                nadac.ingest(conn, run_id, (bad,))
