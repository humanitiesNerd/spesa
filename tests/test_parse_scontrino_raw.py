import json
from pathlib import Path

from scripts.parse_scontrino_raw import parse_raw_lines


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name

    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_conad_base_receipt():
    raw_data = load_fixture("conad_base.raw.json")

    parsed = parse_raw_lines(raw_data["raw_lines"])

    sconto = parsed["discounts"][0]
    assert sconto["amount"] == -1.2



    assert parsed["totals"]["total_amount"] == 10.17

    assert parsed["validation"]["match_total"] is True
    assert parsed["unparsed_lines"] == []

    assert len(parsed["items"]) == 5






    mango = next(
        item for item in parsed["items"]
        if item["description_raw"] == "MANGO S&I GR.380 EST"
    )

    assert mango["gross_amount"] == 4.78
    assert mango["discount_amount"] == -1.2
    assert mango["net_amount"] == 3.58

    assert len(parsed["discounts"]) == 1    

def test_conad_inquadratura_parziale():
    raw_data = load_fixture("conad_header_corrotto.raw.json")

    parsed = parse_raw_lines(raw_data["raw_lines"])

    
    banane = next(
        item
        for item in parsed["items"]
        if item["description_raw"] == "BANANE"
    )

    assert banane["quantity"] == 1.0




def test_conad_receipt_with_missing_header_and_three_decimal_unit_price():
    raw_data = load_fixture("conad_header_mancante.raw.json")

    parsed = parse_raw_lines(raw_data["raw_lines"])

    assert parsed["store"]["brand"] is None
    assert "punto_vendita_non_identificato" in parsed["warnings"]

    assert parsed["totals"]["total_amount"] == 12.62
    assert parsed["validation"]["match_total"] is True
   
    assert parsed["unparsed_lines"] == []

    pomodoro = next(
        item for item in parsed["items"]
        if item["description_raw"] == "POM.TONDO CAMONE S&D"
    )

    assert pomodoro["quantity"] == 2.0
    assert pomodoro["unit_price"] == 1.99
    assert pomodoro["gross_amount"] == 3.98

    
def test_dok_base_receipt_is_supported():
    raw_data = load_fixture("dok_base.raw.json")

    parsed = parse_raw_lines(raw_data["raw_lines"])

    assert parsed["store"]["brand"] == "SUPERMERCATI DOK"
    assert parsed["totals"]["total_amount"] == 7.79

    assert parsed["validation"]["match_total"] is True
    assert "totale_non_validato" not in parsed["warnings"]
    assert parsed["unparsed_lines"] == []
    assert len(parsed["items"]) > 0
