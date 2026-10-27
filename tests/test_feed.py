"""Regresii pentru feed-ul Compari. Datele vin din tests/fixtures/catalog.json, fără rețea.

COMPARIF_OLD_MIN_FILTER=1 aplică filtrul respins (preț sub 74,10 lei scos din feed).
Testul produsului de 7,90 lei trebuie să pice în acel mod și să treacă fără el.
"""
import json
import os
from pathlib import Path

import build_feed as bf

FIXTURE = Path(__file__).parent / "fixtures" / "catalog.json"
REJECTED_MIN = 74.10
CHEAP_ID = "101"


def load_catalog():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def built(catalog=None):
    products = load_catalog() if catalog is None else catalog
    return bf.build(products)


def rows_as_published(rows):
    """Filtrul respins (93 de rânduri) scotea tot ce era sub 74,10 lei."""
    if os.environ.get("COMPARIF_OLD_MIN_FILTER") == "1":
        return [r for r in rows if float(r["Price"]) >= REJECTED_MIN]
    return rows


def by_id(rows):
    return {r["Identifier"]: r for r in rows}


def test_produs_7_90_in_stoc_ramane_in_feed():
    _, rows, excl = built()
    rows = rows_as_published(rows)
    row = by_id(rows).get(CHEAP_ID)
    assert row is not None, "produsul de 7,90 lei, în stoc și eligibil, lipsește din feed"
    assert row["Price"] == "7.90"
    assert row["DeliveryCost"] == "24.90"
    assert CHEAP_ID not in {str(v["id"]) for p, _ in excl for v in p["variants"]}


def test_transport_pe_praguri():
    _, rows, _ = built()
    rows = by_id(rows)
    expect = {
        "102": ("99.00", "24.90"),
        "103": ("298.99", "24.90"),
        "104": ("299.00", "FREE"),
        "105": ("309.90", "FREE"),
    }
    for ident, (price, ship) in expect.items():
        assert rows[ident]["Price"] == price
        assert rows[ident]["DeliveryCost"] == ship
    for row in rows.values():
        assert row["DeliveryCost"] not in bf.INVALID_DELIVERY
        assert row["DeliveryCost"] in (bf.SHIP_COST, bf.FREE_DELIVERY)


def test_produs_indisponibil_exclus_fara_stoc():
    _, rows, excl = built()
    assert "106" not in by_id(rows)
    reasons = {str(v["id"]): why for p, why in excl for v in p["variants"]}
    assert reasons["106"] == "fără stoc"


def test_reconciliere_fiecare_produs_o_singura_data():
    products = load_catalog()
    _, rows, excl = built(products)
    errors = bf.reconciliation_errors(products, rows, excl)
    assert errors == []
    reasons = {}
    for p, why in excl:
        reasons[why] = reasons.get(why, 0) + 1
    assert len(products) == len(rows) + sum(reasons.values())
    assert sum(reasons.values()) == len(excl)
    feed_ids = {r["Identifier"] for r in rows}
    excl_ids = {str(v["id"]) for p, _ in excl for v in p["variants"]}
    assert feed_ids.isdisjoint(excl_ids)
    catalog_ids = {str(v["id"]) for p in products for v in p["variants"]}
    assert feed_ids | excl_ids == catalog_ids


def test_poarta_scadere_peste_30_la_suta_si_prag_400():
    assert bf.MIN_FEED_ROWS == 400
    ok = bf.publish_gate([], [], [], {}, prev_count=1000, new_count=700)
    assert ok == []
    drop = bf.publish_gate([], [], [], {}, prev_count=1000, new_count=699)
    assert any("peste 30%" in e for e in drop)
    floor = bf.publish_gate([], [], [], {}, prev_count=500, new_count=399)
    assert any("400" in e for e in floor)
    assert not any("peste 30%" in e for e in floor)


def test_poarta_id_disparut_fara_motiv_este_listat():
    products = load_catalog()
    catalog_ids = {str(v["id"]) for p in products for v in p["variants"]}
    errors = bf.publish_gate(
        prev_ids=["101", "106"],
        new_ids=["106"],
        catalog_ids=catalog_ids,
        excluded_reasons={"106": "fără stoc"},
        prev_count=500,
        new_count=420,
    )
    assert any("101" in e for e in errors)
    assert any("dispărute" in e for e in errors)

    gone = bf.publish_gate(
        prev_ids=["999"],
        new_ids=[],
        catalog_ids=catalog_ids,
        excluded_reasons={},
        prev_count=500,
        new_count=420,
    )
    assert gone == []

    explained = bf.publish_gate(
        prev_ids=["106"],
        new_ids=[],
        catalog_ids=catalog_ids,
        excluded_reasons={"106": "fără stoc"},
        prev_count=500,
        new_count=420,
    )
    assert explained == []


def test_categorii_pomi_si_seminte():
    _, rows, _ = built()
    rows = by_id(rows)
    assert rows["107"]["Category"] == bf.CAT_FRUIT
    assert rows["109"]["Category"] == bf.CAT_FRUIT
    assert rows["108"]["Category"] == bf.CAT_SEED
    assert rows["108"]["Category"].endswith("Seminte, bulbi")
    assert rows["101"]["Category"] == bf.CAT_PLANT


def test_bulb_in_stoc_este_in_feed():
    _, rows, excl = built()
    row = by_id(rows)["110"]
    assert row["Category"] == bf.CAT_BULB
    assert row["Category"].startswith(bf.CAT_SEED)
    assert "110" not in {str(v["id"]) for p, _ in excl for v in p["variants"]}


def test_bulb_fara_stoc_exclus():
    _, rows, excl = built()
    assert "111" not in by_id(rows)
    reasons = {str(v["id"]): why for p, why in excl for v in p["variants"]}
    assert reasons["111"] == "fără stoc"


def test_delivery_time_2_pe_fiecare_rand():
    _, rows, _ = built()
    assert rows
    assert {r["DeliveryTime"] for r in rows} == {"2"}
