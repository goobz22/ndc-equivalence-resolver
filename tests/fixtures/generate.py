"""Fixture generator — writes the byte-exact test fixture files.

Provenance: the NDC Directory and Orange Book rows are VERBATIM captures
from the real files (ndctext.zip snapshot 2026-08-12; Orange Book July
2026 edition), except where a comment says synthetic. Synthetic rows are
format-faithful and exist to exercise code paths the real slice cannot
(cp1252 encoding byte, OTC-monograph application, Climara Pro combo
product, NADAC dropout series, an estradiol shortage record — none exist
in real data today).

RxNorm RRF lines are constructed from RxNav REST responses verified live
on 2026-08-12 (concept ids 242891/2399898/2110780/1356997/310176 and the
NDC mappings are real; ids >= 999000 are synthetic stand-ins for concepts
whose real ids were not captured).

Run from the repo root:  python tests/fixtures/generate.py
The emitted bytes are committed; .gitattributes marks them -text.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

HERE = Path(__file__).parent
FULL = HERE / "full"
NDC_V2 = HERE / "ndc_v2"

PHARM = "Estradiol Congeners [CS], Estrogen Receptor Agonists [MoA], Estrogen [EPC]"

PRODUCT_HEADER = (
    "PRODUCTID\tPRODUCTNDC\tPRODUCTTYPENAME\tPROPRIETARYNAME\t"
    "PROPRIETARYNAMESUFFIX\tNONPROPRIETARYNAME\tDOSAGEFORMNAME\tROUTENAME\t"
    "STARTMARKETINGDATE\tENDMARKETINGDATE\tMARKETINGCATEGORYNAME\t"
    "APPLICATIONNUMBER\tLABELERNAME\tSUBSTANCENAME\t"
    "ACTIVE_NUMERATOR_STRENGTH\tACTIVE_INGRED_UNIT\tPHARM_CLASSES\t"
    "DEASCHEDULE\tNDC_EXCLUDE_FLAG\tLISTING_RECORD_CERTIFIED_THROUGH"
)

PACKAGE_HEADER = (
    "PRODUCTID\tPRODUCTNDC\tNDCPACKAGECODE\tPACKAGEDESCRIPTION\t"
    "STARTMARKETINGDATE\tENDMARKETINGDATE\tNDC_EXCLUDE_FLAG\tSAMPLE_PACKAGE"
)


def product_row(
    pid: str,
    ndc: str,
    prop: str,
    suffix: str,
    nonprop: str,
    form: str,
    route: str,
    start: str,
    end: str,
    cat: str,
    app: str,
    labeler: str,
    substance: str,
    num: str,
    unit: str,
    pharm: str = PHARM,
    dea: str = "",
    cert: str = "20261231",
) -> str:
    return "\t".join(
        [
            pid, ndc, "HUMAN PRESCRIPTION DRUG", prop, suffix, nonprop, form,
            route, start, end, cat, app, labeler, substance, num, unit, pharm,
            dea, "N", cert,
        ]
    )


PRODUCTS = [
    # --- verbatim rows (2026-08-12 snapshot) ---
    product_row(
        "0378-4642_e1deb37a-8362-4275-a04c-7abcbb2e9f56", "0378-4642",
        "Estradiol", "", "estradiol", "PATCH", "TRANSDERMAL",
        "20141219", "", "ANDA", "ANDA201675", "Mylan Pharmaceuticals Inc.",
        "ESTRADIOL", ".05", "mg/d",
    ),
    product_row(
        "0378-4621_e3b94477-b715-40f6-bbbb-fe52a87148dd", "0378-4621",
        "Estradiol", "", "estradiol", "PATCH", "TRANSDERMAL",
        "20181101", "", "ANDA", "ANDA206685", "Mylan Pharmaceuticals Inc.",
        "ESTRADIOL", ".05", "mg/d",
    ),
    product_row(
        "0378-3350_49f22eba-c5a4-4264-b905-6a8ff7e0d884", "0378-3350",
        "Estradiol", "", "estradiol", "PATCH", "TRANSDERMAL",
        "20000301", "", "ANDA", "ANDA075182", "Mylan Pharmaceuticals Inc.",
        "ESTRADIOL", ".05", "mg/d",
    ),
    product_row(
        "65162-149_6828b547-27f6-4099-981f-a8efcba66370", "65162-149",
        "LYLLANA", "", "Estradiol", "PATCH, EXTENDED RELEASE", "TRANSDERMAL",
        "20200930", "", "ANDA", "ANDA211396", "Amneal Pharmaceuticals LLC",
        "ESTRADIOL", ".05", "mg/d",
    ),
    product_row(
        "65162-993_d26f45d5-79c5-429a-bb0f-44c58fa0b569", "65162-993",
        "DOTTI", "", "Estradiol", "PATCH, EXTENDED RELEASE", "TRANSDERMAL",
        "20190204", "", "ANDA", "ANDA211293", "Amneal Pharmaceuticals LLC",
        "ESTRADIOL", ".05", "mg/d",
    ),
    product_row(
        "66758-147_8e8ae172-5a0d-4888-a825-0c6cfa1afac9", "66758-147",
        "Vivelle-Dot", "", "estradiol", "PATCH, EXTENDED RELEASE", "TRANSDERMAL",
        "19990108", "", "NDA", "NDA020538", "Sandoz Inc",
        "ESTRADIOL", ".05", "mg/d",
    ),
    product_row(
        "68968-6650_0d1f7ac0-2185-451c-bd3f-0a5a67ef8d54", "68968-6650",
        "Minivelle", "", "estradiol", "FILM, EXTENDED RELEASE", "TRANSDERMAL",
        "20121220", "", "NDA", "NDA203752", "Noven Therapeutics, LLC",
        "ESTRADIOL", ".05", "mg/d", cert="20271231",
    ),
    product_row(
        "50419-451_c092f921-73f7-45be-b928-744cfdd24b49", "50419-451",
        "Climara", "", "Estradiol", "PATCH", "TRANSDERMAL",
        "19941222", "", "NDA", "NDA020375",
        "Bayer HealthCare Pharmaceuticals Inc.",
        "ESTRADIOL", ".05", "mg/d", cert="20271231",
    ),
    product_row(  # Menostar — carries Climara's NDA020375 (upstream defect)
        "50419-455_2ace4c5d-880e-4ac1-a5e9-ff8028afc282", "50419-455",
        "Menostar", "", "estradiol", "PATCH", "TRANSDERMAL",
        "20040608", "", "NDA", "NDA020375",
        "Bayer HealthCare Pharmaceuticals Inc.",
        "ESTRADIOL", "14", "ug/d", cert="20271231",
    ),
    product_row(
        "0781-7144_e8503d39-2211-41b4-ab01-1e99bee65e3d", "0781-7144",
        "Estradiol", "", "estradiol", "PATCH, EXTENDED RELEASE", "TRANSDERMAL",
        "20141222", "", "NDA AUTHORIZED GENERIC", "NDA020538", "Sandoz Inc",
        "ESTRADIOL", ".05", "mg/d",
    ),
    product_row(
        "0781-7133_1f2a1b63-ca41-4695-a296-542c1dc04b79", "0781-7133",
        "Estradiol Transdermal System", "", "Estradiol", "PATCH", "TRANSDERMAL",
        "19941222", "", "NDA AUTHORIZED GENERIC", "NDA020375", "Sandoz Inc",
        "ESTRADIOL", ".05", "mg/d", cert="20271231",
    ),
    product_row(
        "70710-1193_51a2adf6-a381-42cb-bf3e-8c83a7cfe738", "70710-1193",
        "Estradiol", "", "Estradiol", "PATCH, EXTENDED RELEASE", "TRANSDERMAL",
        "20230413", "", "ANDA", "ANDA206241", "Zydus Pharmaceuticals USA Inc.",
        "ESTRADIOL", ".05", "mg/d",
    ),
    product_row(
        "68382-326_bc6ecc76-9efc-435a-ac21-b526a971c343", "68382-326",
        "estradiol", "", "estradiol", "PATCH", "TRANSDERMAL",
        "20231102", "", "ANDA", "ANDA202985", "Zydus Pharmaceuticals USA Inc.",
        "ESTRADIOL", ".05", "mg/d",
    ),
    product_row(
        "68025-065_077120b4-1172-49bc-b197-363f410589ab", "68025-065",
        "DIVIGEL", "", "estradiol", "GEL", "TOPICAL",
        "20141027", "", "NDA", "NDA022038", "Vertical Pharmaceuticals, LLC",
        "ESTRADIOL", ".25", "mg/.25g", cert="20271231",
    ),
    product_row(
        "0574-2067_2da3b881-d6b1-4996-889b-cd882108af38", "0574-2067",
        "Evamist", "", "Estradiol", "SPRAY", "TRANSDERMAL",
        "20150411", "", "NDA", "NDA022014", "Padagis US LLC",
        "ESTRADIOL", "1.53", "mg/1",
    ),
    product_row(
        "0555-0886_e9b2e697-6e57-436a-933d-5554ca402da7", "0555-0886",
        "Estradiol", "", "Estradiol", "TABLET", "ORAL",
        "19971028", "", "ANDA", "ANDA040197", "Teva Pharmaceuticals USA, Inc.",
        "ESTRADIOL", "1", "mg/1", cert="20271231",
    ),
    product_row(  # in NDC Directory; its ANDA is deliberately absent from the
        # Orange Book fixture slice → exercises ob_link_status='no-ob-row'
        "21922-015_d03184c7-c726-4356-a643-bd4bdd0f893b", "21922-015",
        "ESTRADIOL", "", "Estradiol", "GEL", "TRANSDERMAL",
        "20260513", "", "ANDA", "ANDA218214", "Encube Ethicals, Inc.",
        "ESTRADIOL", ".75", "mg/1.25g", cert="20271231",
    ),
    # --- synthetic, format-faithful ---
    product_row(  # combo product — the ingredient_set guard case
        "50419-491_synthetic-climara-pro", "50419-491",
        "Climara Pro", "", "estradiol and levonorgestrel",
        "PATCH, EXTENDED RELEASE", "TRANSDERMAL",
        "20041101", "", "NDA", "NDA021258",
        "Bayer HealthCare Pharmaceuticals Inc.",
        "ESTRADIOL; LEVONORGESTREL", ".045; .015", "mg/d; mg/d",
        pharm="Estradiol Congeners [CS], Progestins [CS]",
        cert="20271231",
    ),
    product_row(  # cp1252 labeler byte (0x92) + OTC-monograph application
        "43598-115_synthetic-cp1252-otc", "43598-115",
        "Omeprazole", "", "omeprazole", "TABLET, DELAYED RELEASE", "ORAL",
        "20180501", "", "OTC MONOGRAPH DRUG", "M013",
        "Dr. Reddy’s Laboratories Inc.",
        "OMEPRAZOLE", "20", "mg/1",
        pharm="Proton Pump Inhibitor [EPC]",
    ),
]


def package_row(
    pid: str, ndc: str, code: str, descr: str, start: str,
    end: str = "", sample: str = "N",
) -> str:
    return "\t".join([pid, ndc, code, descr, start, end, "N", sample])


PACKAGES = [
    package_row(
        "0378-4642_e1deb37a-8362-4275-a04c-7abcbb2e9f56", "0378-4642",
        "0378-4642-26",
        "8 POUCH in 1 CARTON (0378-4642-26)  / 1 PATCH in 1 POUCH (0378-4642-16)  / 3.5 d in 1 PATCH",
        "20141219",
    ),
    package_row(
        "0378-4621_e3b94477-b715-40f6-bbbb-fe52a87148dd", "0378-4621",
        "0378-4621-26",
        "8 POUCH in 1 CARTON (0378-4621-26)  / 1 PATCH in 1 POUCH (0378-4621-16)  / 3.5 d in 1 PATCH",
        "20181101",
    ),
    package_row(
        "0378-3350_49f22eba-c5a4-4264-b905-6a8ff7e0d884", "0378-3350",
        "0378-3350-99",
        "4 POUCH in 1 CARTON (0378-3350-99)  / 1 PATCH in 1 POUCH (0378-3350-16)  / 7 d in 1 PATCH",
        "20000301",
    ),
    package_row(
        "65162-149_6828b547-27f6-4099-981f-a8efcba66370", "65162-149",
        "65162-149-08",
        "8 POUCH in 1 CARTON (65162-149-08)  / 1 d in 1 POUCH (65162-149-04) ",
        "20200930",
    ),
    package_row(
        "65162-993_d26f45d5-79c5-429a-bb0f-44c58fa0b569", "65162-993",
        "65162-993-08",
        "8 POUCH in 1 CARTON (65162-993-08)  / 1 d in 1 POUCH (65162-993-04) ",
        "20190204",
    ),
    package_row(
        "66758-147_8e8ae172-5a0d-4888-a825-0c6cfa1afac9", "66758-147",
        "66758-147-83",
        "8 POUCH in 1 BOX (66758-147-83)  / 1 PATCH in 1 POUCH (66758-147-58)  / 3.5 d in 1 PATCH",
        "20250217",
    ),
    package_row(
        "68968-6650_0d1f7ac0-2185-451c-bd3f-0a5a67ef8d54", "68968-6650",
        "68968-6650-8",
        "8 POUCH in 1 PACKET (68968-6650-8)  / 1 d in 1 POUCH",
        "20121220",
    ),
    package_row(
        "50419-451_c092f921-73f7-45be-b928-744cfdd24b49", "50419-451",
        "50419-451-04",
        "4 PATCH in 1 CARTON (50419-451-04)  / 7 d in 1 PATCH (50419-451-01) ",
        "19941222",
    ),
    package_row(
        "50419-455_2ace4c5d-880e-4ac1-a5e9-ff8028afc282", "50419-455",
        "50419-455-04",
        "4 PATCH in 1 CARTON (50419-455-04)  / 7 d in 1 PATCH",
        "20040608",
    ),
    package_row(
        "0781-7144_e8503d39-2211-41b4-ab01-1e99bee65e3d", "0781-7144",
        "0781-7144-83",
        "8 POUCH in 1 CARTON (0781-7144-83)  / 1 PATCH in 1 POUCH (0781-7144-58)  / 3.5 d in 1 PATCH",
        "20141222",
    ),
    package_row(
        "0781-7133_1f2a1b63-ca41-4695-a296-542c1dc04b79", "0781-7133",
        "0781-7133-54",
        "4 PATCH in 1 CARTON (0781-7133-54)  / 7 d in 1 PATCH (0781-7133-58) ",
        "20180831",
    ),
    package_row(
        "70710-1193_51a2adf6-a381-42cb-bf3e-8c83a7cfe738", "70710-1193",
        "70710-1193-8",
        "8 POUCH in 1 BOX (70710-1193-8)  / 1 PATCH in 1 POUCH (70710-1193-1)  / 3.5 d in 1 PATCH",
        "20230413",
    ),
    package_row(
        "68382-326_bc6ecc76-9efc-435a-ac21-b526a971c343", "68382-326",
        "68382-326-04",
        "4 POUCH in 1 CARTON (68382-326-04)  / 1 PATCH in 1 POUCH (68382-326-01)  / 7 d in 1 PATCH",
        "20231102",
    ),
    package_row(
        "68025-065_077120b4-1172-49bc-b197-363f410589ab", "68025-065",
        "68025-065-07",
        "7 PACKET in 1 CARTON (68025-065-07)  / .25 g in 1 PACKET",
        "20141027",
    ),
    package_row(
        "68025-065_077120b4-1172-49bc-b197-363f410589ab", "68025-065",
        "68025-065-30",
        "30 PACKET in 1 CARTON (68025-065-30)  / .25 g in 1 PACKET",
        "20141027",
    ),
    package_row(
        "0574-2067_2da3b881-d6b1-4996-889b-cd882108af38", "0574-2067",
        "0574-2067-00",
        "56 SPRAY in 1 VIAL, MULTI-DOSE (0574-2067-00) ",
        "20150411", sample="Y",
    ),
    package_row(
        "0574-2067_2da3b881-d6b1-4996-889b-cd882108af38", "0574-2067",
        "0574-2067-27",
        "56 SPRAY in 1 VIAL, MULTI-DOSE (0574-2067-27) ",
        "20150411",
    ),
    package_row(
        "0555-0886_e9b2e697-6e57-436a-933d-5554ca402da7", "0555-0886",
        "0555-0886-02",
        "100 TABLET in 1 BOTTLE (0555-0886-02) ",
        "19971028",
    ),
    package_row(
        "0555-0886_e9b2e697-6e57-436a-933d-5554ca402da7", "0555-0886",
        "0555-0886-04",
        "500 TABLET in 1 BOTTLE (0555-0886-04) ",
        "19971028",
    ),
    package_row(
        "21922-015_d03184c7-c726-4356-a643-bd4bdd0f893b", "21922-015",
        "21922-015-40",
        "1 BOTTLE, PUMP in 1 CARTON (21922-015-40)  / 50 g in 1 BOTTLE, PUMP",
        "20260513",
    ),
    package_row(
        "50419-491_synthetic-climara-pro", "50419-491",
        "50419-491-04",
        "4 PATCH in 1 CARTON (50419-491-04)  / 7 d in 1 PATCH",
        "20041101",
    ),
    package_row(
        "43598-115_synthetic-cp1252-otc", "43598-115",
        "43598-115-90",
        "90 TABLET, DELAYED RELEASE in 1 BOTTLE (43598-115-90) ",
        "20180501",
    ),
]

OB_HEADER = (
    "Ingredient~DF;Route~Trade_Name~Applicant~Strength~Appl_Type~Appl_No~"
    "Product_No~TE_Code~Approval_Date~RLD~RS~Type~Applicant_Full_Name"
)

OB_ROWS = [
    # --- AB1 heading: SYSTEM;TRANSDERMAL (verbatim, July 2026 edition) ---
    "ESTRADIOL~SYSTEM;TRANSDERMAL~VIVELLE-DOT~SANDOZ~0.05MG/24HR~N~020538~006~AB1~Jan 8, 1999~Yes~No~RX~SANDOZ INC",
    "ESTRADIOL~SYSTEM;TRANSDERMAL~VIVELLE-DOT~SANDOZ~0.1MG/24HR~N~020538~008~AB1~Jan 8, 1999~Yes~Yes~RX~SANDOZ INC",
    "ESTRADIOL~SYSTEM;TRANSDERMAL~ESTRADIOL~MYLAN TECHNOLOGIES~0.05MG/24HR~A~201675~003~AB1~Dec 19, 2014~No~No~RX~MYLAN TECHNOLOGIES INC",
    "ESTRADIOL~SYSTEM;TRANSDERMAL~ESTRADIOL~MYLAN TECHNOLOGIES~0.1MG/24HR~A~201675~005~AB1~Dec 19, 2014~No~No~RX~MYLAN TECHNOLOGIES INC",
    "ESTRADIOL~SYSTEM;TRANSDERMAL~ESTRADIOL~AMNEAL~0.05MG/24HR~A~211293~003~AB1~Feb 4, 2019~No~No~RX~AMNEAL PHARMACEUTICALS LLC",
    "ESTRADIOL~SYSTEM;TRANSDERMAL~ESTRADIOL~ZYDUS PHARMS~0.05MG/24HR~A~206241~003~AB1~Dec 1, 2022~No~No~RX~ZYDUS PHARMACEUTICALS USA INC",
    "ESTRADIOL~SYSTEM;TRANSDERMAL~MENOSTAR~BAYER HLTHCARE~0.014MG/24HR~N~021674~001~AB~Jun 8, 2004~Yes~Yes~RX~BAYER HEALTHCARE PHARMACEUTICALS INC",
    "ESTRADIOL~SYSTEM;TRANSDERMAL~ESTRADIOL~ZYDUS PHARMS~0.014MG/24HR~A~204379~001~AB~Apr 17, 2023~No~No~RX~ZYDUS PHARMACEUTICALS USA INC",
    # --- AB2 / AB3 heading: FILM, EXTENDED RELEASE;TRANSDERMAL (verbatim) ---
    "ESTRADIOL~FILM, EXTENDED RELEASE;TRANSDERMAL~CLIMARA~BAYER HLTHCARE~0.05MG/24HR~N~020375~001~AB2~Dec 22, 1994~Yes~No~RX~BAYER HEALTHCARE PHARMACEUTICALS INC",
    "ESTRADIOL~FILM, EXTENDED RELEASE;TRANSDERMAL~ESTRADIOL~MYLAN TECHNOLOGIES~0.05MG/24HR~A~075182~006~AB2~Feb 24, 2000~No~No~RX~MYLAN TECHNOLOGIES INC",
    "ESTRADIOL~FILM, EXTENDED RELEASE;TRANSDERMAL~ESTRADIOL~ZYDUS PHARMS~0.05MG/24HR~A~202985~003~AB2~Mar 29, 2023~No~No~RX~ZYDUS PHARMACEUTICALS USA INC",
    "ESTRADIOL~FILM, EXTENDED RELEASE;TRANSDERMAL~MINIVELLE~NOVEN~0.05MG/24HR~N~203752~003~AB3~Oct 29, 2012~Yes~No~RX~NOVEN PHARMACEUTICALS INC",
    "ESTRADIOL~FILM, EXTENDED RELEASE;TRANSDERMAL~ESTRADIOL~AMNEAL~0.05MG/24HR~A~211396~003~AB3~Sep 28, 2020~No~No~RX~AMNEAL PHARMACEUTICALS LLC",
    "ESTRADIOL~FILM, EXTENDED RELEASE;TRANSDERMAL~ESTRADIOL~MYLAN TECHNOLOGIES~0.05MG/24HR~A~206685~003~AB3~Aug 15, 2018~No~No~RX~MYLAN TECHNOLOGIES INC",
    # --- DISCN rows, blank TE (verbatim) ---
    "ESTRADIOL~FILM, EXTENDED RELEASE;TRANSDERMAL~ALORA~ABBVIE~0.05MG/24HR~N~020655~001~~Dec 20, 1996~No~No~DISCN~ABBVIE INC",
    "ESTRADIOL~SYSTEM;TRANSDERMAL~ESTRADERM~NOVARTIS~0.05MG/24HR~N~019081~002~~Sep 10, 1986~Yes~No~DISCN~NOVARTIS PHARMACEUTICALS CORP",
    "ESTRADIOL~SYSTEM;TRANSDERMAL~VIVELLE~SANDOZ~0.05MG/24HR~N~020323~002~~Oct 28, 1994~No~No~DISCN~SANDOZ INC",
    # --- gel / spray / oral contrast rows (verbatim) ---
    "ESTRADIOL~GEL;TRANSDERMAL~DIVIGEL~VERTICAL PHARMS~0.1% (0.25GM/PACKET)~N~022038~001~AB~Jun 4, 2007~Yes~Yes~RX~VERTICAL PHARMACEUTICALS LLC",
    "ESTRADIOL~GEL;TRANSDERMAL~DIVIGEL~VERTICAL PHARMS~0.1% (1GM/PACKET)~N~022038~003~AB~Jun 4, 2007~Yes~Yes~RX~VERTICAL PHARMACEUTICALS LLC",
    "ESTRADIOL~SPRAY;TRANSDERMAL~EVAMIST~PADAGIS US~1.53MG/SPRAY~N~022014~001~~Jul 27, 2007~Yes~Yes~RX~PADAGIS US LLC",
    "ESTRADIOL~TABLET;ORAL~ESTRADIOL~BARR LABS INC~1MG~A~040197~002~AB~Oct 22, 1997~No~No~RX~BARR LABORATORIES INC",
    # synthetic: FR-suffix + pre-1982 date in one row (both real OB features)
    "ESTRADIOL~TABLET;ORAL~ESTRACE~ALLERGAN~0.5MG **Federal Register determination that product was not discontinued or withdrawn for safety or effectiveness reasons**~N~084499~001~~Approved Prior to Jan 1, 1982~No~No~DISCN~ALLERGAN SALES LLC",
    # synthetic combo (format-faithful; real Climara Pro is N021258)
    "ESTRADIOL; LEVONORGESTREL~FILM, EXTENDED RELEASE;TRANSDERMAL~CLIMARA PRO~BAYER HLTHCARE~0.045MG/24HR;0.015MG/24HR~N~021258~001~~Nov 4, 2004~Yes~Yes~RX~BAYER HEALTHCARE PHARMACEUTICALS INC",
]

# ---------------------------------------------------------------- RxNorm RRF

_CONCEPTS = [
    # (rxcui, tty, name) — ids < 999000 verified live via RxNav 2026-08-12
    ("242891", "SCD", "84 HR estradiol 0.00208 MG/HR Transdermal System"),
    ("242892", "SCD", "168 HR estradiol 0.00208 MG/HR Transdermal System"),
    ("2399898", "SBD", "84 HR estradiol 0.00208 MG/HR Transdermal System [Lyllana]"),
    ("2110780", "SBD", "84 HR estradiol 0.00208 MG/HR Transdermal System [Dotti]"),
    ("1356997", "SBD", "84 HR estradiol 0.00208 MG/HR Transdermal System [Minivelle]"),
    ("310176", "SBD", "84 HR estradiol 0.00208 MG/HR Transdermal System [Vivelle]"),
    ("4083", "IN", "estradiol"),
    ("6373", "IN", "levonorgestrel"),
    # synthetic ids (real concepts exist; ids not captured):
    ("999001", "SBD", "168 HR estradiol 0.00208 MG/HR Transdermal System [Climara]"),
    ("999002", "SBD", "84 HR estradiol 0.00208 MG/HR Transdermal System [Alora]"),
    ("999003", "SBD", "84 HR estradiol 0.00208 MG/HR Transdermal System [Vivelle-Dot]"),
    ("999100", "SCD", "estradiol 0.00188 MG/HR / levonorgestrel 0.000625 MG/HR Weekly Transdermal System"),
    ("197659", "SCD", "estradiol 1 MG Oral Tablet"),
    ("999300", "SCD", "estradiol 1 MG/GM Topical Gel"),
    ("999400", "SCD", "estradiol 1.53 MG/ACTUAT Metered Dose Transdermal Spray"),
]

_RELS = [
    # (rxcui1, rela, rxcui2) — queried in both directions by the resolver
    ("2399898", "tradename_of", "242891"),
    ("2110780", "tradename_of", "242891"),
    ("1356997", "tradename_of", "242891"),
    ("310176", "tradename_of", "242891"),
    ("999003", "tradename_of", "242891"),
    ("999002", "tradename_of", "242891"),
    ("999001", "tradename_of", "242892"),
    ("242891", "has_ingredient", "4083"),
    ("242892", "has_ingredient", "4083"),
    ("999100", "has_ingredient", "4083"),
    ("999100", "has_ingredient", "6373"),
    ("197659", "has_ingredient", "4083"),
    ("999300", "has_ingredient", "4083"),
    ("999400", "has_ingredient", "4083"),
]

_NDC_MAP = [
    # (ndc11, rxcui) — verified via RxNav ndcstatus/ndcs.json 2026-08-12
    # except the 999* synthetic-concept rows and Alora (historical NDC,
    # kept to exercise the rxnorm-only-seed path)
    ("00378464226", "242891"),
    ("00378462126", "242891"),  # Mylan AB3 NDC — RxNorm cannot see AB1 vs AB3
    ("00781714483", "242891"),
    ("70710119308", "242891"),
    ("65162014908", "2399898"),
    ("65162099308", "2110780"),
    ("68968665008", "1356997"),
    ("66758014783", "999003"),
    ("50419045104", "999001"),
    ("00378335099", "242892"),
    ("68382032604", "242892"),
    ("52544047108", "999002"),  # Alora — absent from the NDC Directory
    ("50419049104", "999100"),  # Climara Pro combo
    ("00555088602", "197659"),
    ("68025006507", "999300"),
    ("00574206727", "999400"),
]


def rxnconso_line(rxcui: str, tty: str, name: str) -> str:
    fields = [""] * 18
    fields[0] = rxcui
    fields[1] = "ENG"
    fields[7] = f"A{rxcui}"
    fields[11] = "RXNORM"
    fields[12] = tty
    fields[13] = rxcui
    fields[14] = name
    fields[16] = "N"
    fields[17] = "4096"
    return "|".join(fields)


def rxnrel_line(rxcui1: str, rela: str, rxcui2: str) -> str:
    fields = [""] * 16
    fields[0] = rxcui1
    fields[2] = "CUI"
    fields[3] = "RB"
    fields[4] = rxcui2
    fields[6] = "CUI"
    fields[7] = rela
    fields[10] = "RXNORM"
    fields[14] = "N"
    return "|".join(fields)


def rxnsat_line(ndc11: str, rxcui: str) -> str:
    fields = [""] * 13
    fields[0] = rxcui
    fields[3] = f"A{rxcui}"
    fields[4] = "AUI"
    fields[5] = rxcui
    fields[8] = "NDC"
    fields[9] = "RXNORM"
    fields[10] = ndc11
    fields[11] = "N"
    fields[12] = "4096"
    return "|".join(fields)


# ------------------------------------------------------------------- NADAC

NADAC_HEADER = [
    "NDC Description", "NDC", "NADAC Per Unit", "Effective Date",
    "Pricing Unit", "Pharmacy Type Indicator", "OTC", "Explanation Code",
    "Classification for Rate Setting",
    "Corresponding Generic Drug NADAC Per Unit",
    "Corresponding Generic Drug Effective Date", "As of Date",
]

_SNAPSHOTS_2026 = [
    "01/07/2026", "02/11/2026", "03/11/2026", "04/08/2026",
    "05/13/2026", "06/17/2026", "07/22/2026", "08/12/2026",
]

# (description, ndc11, [(effective MM/DD/YYYY, price)], last_snapshot_index or None)
_NADAC_2026_SERIES: list[tuple[str, str, list[tuple[str, str]], int | None, str]] = [
    # Anchor family — real price points (2026 NADAC file), all class-priced G
    ("ESTRADIOL 0.05 MG PATCH (2/WK)", "00378464226",
     [("12/17/2025", "7.24742"), ("02/18/2026", "7.25512"),
      ("04/22/2026", "7.33071"), ("05/20/2026", "7.69084"),
      ("06/17/2026", "7.76775"), ("07/22/2026", "7.97659")], None, "1"),
    ("LYLLANA 0.05 MG PATCH", "65162014908",
     [("12/17/2025", "7.24742"), ("02/18/2026", "7.25512"),
      ("04/22/2026", "7.33071"), ("05/20/2026", "7.69084"),
      ("06/17/2026", "7.76775"), ("07/22/2026", "7.97659")], None, "1"),
    ("DOTTI 0.05 MG PATCH", "65162099308",
     [("12/17/2025", "7.24742"), ("02/18/2026", "7.25512"),
      ("04/22/2026", "7.33071"), ("05/20/2026", "7.69084"),
      ("06/17/2026", "7.76775"), ("07/22/2026", "7.97659")], None, "1"),
    ("ESTRADIOL 0.05 MG PATCH (2/WK)", "00781714483",
     [("12/17/2025", "7.24742"), ("07/22/2026", "7.97659")], None, "1"),
    # SYNTHETIC dropout: Zydus AB1 stops appearing after the 06/17 snapshot
    ("ESTRADIOL 0.05 MG PATCH (2/WK)", "70710119308",
     [("12/17/2025", "7.24742"), ("04/22/2026", "7.33071")], 5, "1, 5"),
    ("VIVELLE-DOT 0.05 MG PATCH", "66758014783",
     [("12/17/2025", "15.51000")], None, "1"),
    ("MINIVELLE 0.05 MG PATCH", "68968665008",
     [("12/17/2025", "16.24000")], None, "1"),
    ("CLIMARA 0.05 MG PATCH", "50419045104",
     [("12/17/2025", "12.10000")], None, "1"),
    ("ESTRADIOL 0.05 MG PATCH (1/WK)", "00378335099",
     [("12/17/2025", "6.81000")], None, "1"),
    ("ESTRADIOL 0.05 MG PATCH (1/WK)", "68382032604",
     [("12/17/2025", "6.81000")], None, "1"),
    ("ESTRADIOL 1 MG TABLET", "00555088602",
     [("12/17/2025", "0.03642")], None, "1"),
]

_NADAC_2025_SERIES: list[tuple[str, str, list[tuple[str, str]], int | None, str]] = [
    ("ESTRADIOL 0.05 MG PATCH (2/WK)", "00378464226",
     [("12/18/2024", "5.98844"), ("06/18/2025", "6.51000")], None, "1"),
    ("LYLLANA 0.05 MG PATCH", "65162014908",
     [("12/18/2024", "5.98844"), ("06/18/2025", "6.51000")], None, "1"),
    ("DOTTI 0.05 MG PATCH", "65162099308",
     [("12/18/2024", "5.98844"), ("06/18/2025", "6.51000")], None, "1"),
]

_SNAPSHOTS_2025 = ["01/08/2025", "07/09/2025"]


def _mmddyyyy_key(date: str) -> tuple[int, int, int]:
    month, day, year = date.split("/")
    return int(year), int(month), int(day)


def nadac_csv(
    series: list[tuple[str, str, list[tuple[str, str]], int | None, str]],
    snapshots: list[str],
) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(NADAC_HEADER)
    for description, ndc11, points, last_index, explanation in series:
        for index, snapshot in enumerate(snapshots):
            if last_index is not None and index >= last_index:
                continue
            current = [
                (eff, price)
                for eff, price in points
                if _mmddyyyy_key(eff) <= _mmddyyyy_key(snapshot)
            ]
            if not current:
                continue
            effective, price = max(current, key=lambda p: _mmddyyyy_key(p[0]))
            writer.writerow(
                [description, ndc11, price, effective, "EA", "C/I", "N",
                 explanation, "G", "", "", snapshot]
            )
    return buffer.getvalue()


# ---------------------------------------------------------------- shortages

SHORTAGES_JSON = """{
  "meta": {"last_updated": "2026-08-12", "results": {"total": 4}},
  "results": [
    {
      "update_type": "Reverified",
      "initial_posting_date": "10/31/2017",
      "package_ndc": "0409-1304-31",
      "generic_name": "Hydromorphone Hydrochloride Injection",
      "availability": "Available",
      "update_date": "08/07/2026",
      "therapeutic_category": ["Analgesia/Addiction"],
      "dosage_form": "Injection",
      "company_name": "Hospira, Inc., a Pfizer Company",
      "status": "Current"
    },
    {
      "update_type": "New",
      "initial_posting_date": "05/30/2025",
      "package_ndc": "61314-531-64",
      "generic_name": "Amoxicillin Oral Suspension",
      "availability": "Unvailable",
      "shortage_reason": "Demand increase for the drug",
      "update_date": "07/15/2026",
      "dosage_form": "Suspension",
      "company_name": "Sandoz Inc",
      "status": "Current"
    },
    {
      "update_type": "New",
      "initial_posting_date": "01/13/2026",
      "package_ndc": "0071-0530-23",
      "generic_name": "Phenytoin Extended Release Capsule",
      "availability": "Limited Availability",
      "update_date": "03/02/2026",
      "dosage_form": "Capsule",
      "company_name": "Pfizer Inc.",
      "status": "Current"
    },
    {
      "update_type": "Revised",
      "initial_posting_date": "01/13/2026",
      "package_ndc": "0071-0530-23",
      "generic_name": "Phenytoin Extended Release Capsule",
      "availability": "Available",
      "update_date": "06/20/2026",
      "dosage_form": "Capsule",
      "company_name": "Pfizer Inc.",
      "status": "Resolved"
    }
  ]
}
"""

SHORTAGES_SYNTHETIC_ESTRADIOL = """{
  "meta": {"last_updated": "2026-08-12", "results": {"total": 1}},
  "results": [
    {
      "update_type": "New",
      "initial_posting_date": "04/15/2026",
      "package_ndc": "0378-4642-26",
      "generic_name": "Estradiol Transdermal System",
      "availability": "Unavailable",
      "shortage_reason": "Demand increase for the drug",
      "update_date": "07/30/2026",
      "dosage_form": "Patch",
      "company_name": "Mylan Pharmaceuticals Inc.",
      "status": "Current"
    }
  ]
}
"""


def _write_crlf(path: Path, lines: list[str], encoding: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = "\r\n".join(lines) + "\r\n"
    path.write_bytes(data.encode(encoding))


def main() -> None:
    _write_crlf(FULL / "product.txt", [PRODUCT_HEADER] + PRODUCTS, "cp1252")
    _write_crlf(FULL / "package.txt", [PACKAGE_HEADER] + PACKAGES, "ascii")
    _write_crlf(FULL / "products.txt", [OB_HEADER] + OB_ROWS, "ascii")

    (FULL / "RXNCONSO.RRF").write_bytes(
        ("\n".join(rxnconso_line(*c) for c in _CONCEPTS) + "\n").encode("utf-8")
    )
    (FULL / "RXNREL.RRF").write_bytes(
        ("\n".join(rxnrel_line(*r) for r in _RELS) + "\n").encode("utf-8")
    )
    (FULL / "RXNSAT.RRF").write_bytes(
        ("\n".join(rxnsat_line(*n) for n in _NDC_MAP) + "\n").encode("utf-8")
    )

    (FULL / "nadac_2025.csv").write_bytes(
        nadac_csv(_NADAC_2025_SERIES, _SNAPSHOTS_2025).encode("utf-8")
    )
    (FULL / "nadac_2026.csv").write_bytes(
        nadac_csv(_NADAC_2026_SERIES, _SNAPSHOTS_2026).encode("utf-8")
    )

    (FULL / "shortages.json").write_bytes(SHORTAGES_JSON.encode("utf-8"))
    (HERE / "shortages_synthetic_estradiol.json").write_bytes(
        SHORTAGES_SYNTHETIC_ESTRADIOL.encode("utf-8")
    )

    # Mutation fixture v2: one row modified (LYLLANA renamed), one product
    # removed entirely (Evamist + its packages) — proves atomic-replace
    # propagates upstream deletions, which upsert-only refresh would miss.
    v2_products = [
        row.replace("LYLLANA", "LYLLANA XR") if "\tLYLLANA\t" in row else row
        for row in PRODUCTS
        if "0574-2067" not in row
    ]
    v2_packages = [row for row in PACKAGES if "0574-2067" not in row]
    _write_crlf(NDC_V2 / "product.txt", [PRODUCT_HEADER] + v2_products, "cp1252")
    _write_crlf(NDC_V2 / "package.txt", [PACKAGE_HEADER] + v2_packages, "ascii")

    print(f"fixtures written under {HERE}")


if __name__ == "__main__":
    main()
