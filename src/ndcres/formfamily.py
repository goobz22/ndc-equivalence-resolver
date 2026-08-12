"""Delivery form-family classification.

Neither dataset's raw strings can be compared across sources:

    NDC Directory: PATCH · PATCH, EXTENDED RELEASE · FILM, EXTENDED RELEASE
                   all mean "transdermal patch", inconsistently per labeler
    Orange Book:   SYSTEM;TRANSDERMAL and FILM, EXTENDED RELEASE;TRANSDERMAL
                   are the same physical class split by application era
    Routes:        Divigel/EstroGel are TOPICAL in the NDC Directory but
                   TRANSDERMAL in the Orange Book

So each source maps its own strings into one shared curated vocabulary,
and cross-source logic compares only the family value. The family is a
coarse delivery class (Tier-4 boundary), NOT an equivalence claim.
"""

from __future__ import annotations

_PATCH_FORMS = {
    "PATCH",
    "PATCH, EXTENDED RELEASE",
    "FILM, EXTENDED RELEASE",  # transdermal films only — see route guard
    "SYSTEM",
}
_GEL_FORMS = {"GEL", "GEL, METERED"}
_SPRAY_FORMS = {"SPRAY", "SPRAY, METERED"}
_TABLET_FORMS_PREFIX = ("TABLET", "CAPSULE")
_CREAM_FORMS = {"CREAM", "OINTMENT", "LOTION"}
_VAGINAL_FORMS = {"INSERT", "RING", "SUPPOSITORY"}
_INJECTION_PREFIX = ("INJECTION", "INJECTABLE", "SOLUTION, INJECTION")


def form_family(dosage_form: str | None, route: str | None) -> str | None:
    """Map a (dosage form, route) pair from either source to a family."""
    if not dosage_form:
        return None
    form = dosage_form.strip().upper()
    route_norm = (route or "").strip().upper()

    if form in _PATCH_FORMS:
        # FILM without a transdermal route is a different product class
        # (e.g. buccal films); require the transdermal route for films.
        if form.startswith("FILM") and route_norm and route_norm != "TRANSDERMAL":
            return f"other:{form.lower()}"
        return "patch"
    if form in _GEL_FORMS:
        return "gel"
    if form in _SPRAY_FORMS:
        return "spray"
    if form.startswith(_TABLET_FORMS_PREFIX):
        return "oral-solid" if route_norm in {"", "ORAL"} else f"other:{form.lower()}"
    if form in _CREAM_FORMS:
        return "cream"
    if form in _VAGINAL_FORMS or route_norm == "VAGINAL":
        return "vaginal"
    if form.startswith(_INJECTION_PREFIX):
        return "injection"
    return f"other:{form.lower()}"


def ob_form_family(df_route: str) -> str | None:
    """Map an Orange Book compound 'DF;Route' field to a family."""
    if ";" in df_route:
        form, route = df_route.split(";", 1)
    else:
        form, route = df_route, ""
    return form_family(form, route)
