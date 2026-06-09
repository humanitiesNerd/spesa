from pathlib import Path
from datetime import datetime
import json
import re
import sys







from scripts.receipt_grammars.common import (
    PRICE_RE,
    UNIT_PRICE_RE,
    VAT_RE,
    DISCOUNT_AMOUNT_RE,
    TOTAL_RE,
    IVA_TOTAL_RE,
    PAYMENT_RE,
    DOCUMENT_RE,
    DATETIME_RE,
    PIVA_RE,
    WEIGHT_QTY_RE,
    SERVICE_RE,
)

from scripts.receipt_grammars.dok import DOK_INFO_LINE_RE




PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARSED_DIR = PROJECT_ROOT / "parsed_receipts"


ITEM_RE = re.compile(rf"^(?P<desc>.+?)\s+(?P<iva>{VAT_RE})\s+(?P<price>{PRICE_RE})$")

QTY_RE = re.compile(rf"^(?P<qty>\d+)\s*x\s*(?P<unit>{UNIT_PRICE_RE})\s*EUR$")
DISCOUNT_RE = re.compile(rf"^\*\s*(?P<desc>.+?)\s+(?P<iva>\d+%)\s+(?P<amount>{DISCOUNT_AMOUNT_RE})$")


FILENAME_TIMESTAMP_RE = re.compile(
    r"(?P<date>\d{8})[_-]?(?P<time>\d{6})"
)


def euro_to_float(value: str) -> float:
    return float(value.replace(",", "."))


def parse_datetime(date_value: str, time_value: str) -> str:
    parsed = datetime.strptime(
        f"{date_value} {time_value}",
        "%d-%m-%Y %H:%M",
    )
    return parsed.isoformat(timespec="seconds")


def filename_timestamp(path: Path) -> str | None:
    match = FILENAME_TIMESTAMP_RE.search(path.name)

    if not match:
        return None

    value = f"{match.group('date')} {match.group('time')}"
    parsed = datetime.strptime(value, "%Y%m%d %H%M%S")
    return parsed.isoformat(timespec="seconds")


def receipt_id_from_input_path(path: Path) -> str:
    match = FILENAME_TIMESTAMP_RE.search(path.name)

    if match:
        return f"{match.group('date')}_{match.group('time')}"

    stem = path.stem
    if stem.endswith(".raw"):
        stem = stem.removesuffix(".raw")

    return stem


def output_stem_from_input_path(path: Path) -> str:
    stem = path.stem

    if stem.endswith(".raw"):
        stem = stem.removesuffix(".raw")

    return stem


def is_items_header(line: str) -> bool:
    upper_line = line.upper()
    return "IVA" in upper_line and "PREZZO" in upper_line


def is_probable_receipt_body_line(line: str) -> bool:
    return (
        is_items_header(line)
        or ITEM_RE.match(line) is not None
        or QTY_RE.match(line) is not None
        or DISCOUNT_RE.match(line) is not None
        or TOTAL_RE.match(line) is not None
        or WEIGHT_QTY_RE.match(line) is not None
        or SERVICE_RE.match(line) is not None
    )

def is_separator_line(line: str) -> bool:
    return bool(re.fullmatch(r"-{5,}", line.strip()))

def empty_metadata() -> dict:
    return {
        "negozio": {
            "nome": None,
            "ragione_sociale": None,
            "indirizzo": None,
            "piva": None,
        },
        "data_ora": None,
        "numero_documento": None,
        "pagamento": None,
        "iva_totale": None,
    }





def source_images_from_input(data: dict, input_path: Path) -> list[dict]:
    source_images = data.get("source_images")

    if isinstance(source_images, list) and source_images:
        return source_images

    return [
        {
            "filename": input_path.name,
            "timestamp": filename_timestamp(input_path),
        }
    ]


def parse_metadata(raw_lines: list[str]) -> tuple[dict, list[str]]:
    metadata = empty_metadata()
    warnings = []
    header_lines = []

    for raw_line in raw_lines:
        line = raw_line.strip()

        if not line:
            continue

        if is_probable_receipt_body_line(line):
            break

        header_lines.append(line)

    if not header_lines:
        warnings.append("intestazione_negozio_mancante")
        warnings.append("punto_vendita_non_identificato")
    else:
        metadata["negozio"]["nome"] = header_lines[0]

        if len(header_lines) > 1:
            metadata["negozio"]["ragione_sociale"] = header_lines[1]

    for raw_line in raw_lines:
        line = raw_line.strip()

        if not line:
            continue

        if (
            metadata["negozio"]["indirizzo"] is None
            and (
                line.lower().startswith("via ")
                or line.lower().startswith("viale ")
                or line.lower().startswith("corso ")
                or line.lower().startswith("piazza ")
            )
        ):
            metadata["negozio"]["indirizzo"] = line
            continue

        piva_match = PIVA_RE.match(line)
        if piva_match:
            metadata["negozio"]["piva"] = piva_match.group("piva")
            continue

        datetime_match = DATETIME_RE.match(line)
        if datetime_match:
            metadata["data_ora"] = parse_datetime(
                datetime_match.group("date"),
                datetime_match.group("time"),
            )
            continue

        document_match = DOCUMENT_RE.match(line)
        if document_match:
            metadata["numero_documento"] = document_match.group("number").strip()
            continue

        iva_total_match = IVA_TOTAL_RE.match(line)
        if iva_total_match:
            metadata["iva_totale"] = euro_to_float(iva_total_match.group("iva"))
            continue

        payment_match = PAYMENT_RE.match(line)
        if payment_match:
            metadata["pagamento"] = {
                "metodo": payment_match.group("method").strip(),
                "importo": euro_to_float(payment_match.group("amount")),
            }
            continue

    negozio = metadata["negozio"]

    if (
        negozio["nome"] is None
        or negozio["indirizzo"] is None
        or negozio["piva"] is None
    ):
        if "punto_vendita_non_identificato" not in warnings:
            warnings.append("punto_vendita_non_identificato")

    return metadata, warnings



def vat_rate_to_int(value: str) -> int:
    normalized = value.removesuffix("%").replace(",", ".")
    return int(float(normalized))

def split_receipt_datetime(value: str | None) -> dict:
    if value is None:
        return {
            "date": None,
            "time": None,
        }

    parsed = datetime.fromisoformat(value)

    return {
        "date": parsed.date().isoformat(),
        "time": parsed.time().isoformat(timespec="minutes"),
    }



def parse_raw_lines(
    raw_lines: list[str],
    input_path: Path | None = None,
    source_images: list[dict] | None = None,
) -> dict:

    if input_path is None:
       input_path = Path("test_receipt.raw.json")

    if source_images is None:
        source_images = [
            {
                "filename": input_path.name,
                "timestamp": filename_timestamp(input_path),
            }
        ]

        
    metadata, warnings = parse_metadata(raw_lines)

    items = []
    discounts = []
    unparsed_lines = []

    pending_qty = None
    total = None
    in_items_area = False

    for line_index, raw_line in enumerate(raw_lines):
        line = raw_line.strip()

        if not line or is_separator_line(line):
            continue

        if DOK_INFO_LINE_RE.match(line):
            continue

        if is_items_header(line):
            in_items_area = True
            continue

        total_match = TOTAL_RE.match(line)
        if total_match:
            total = euro_to_float(total_match.group("total"))
            in_items_area = False
            continue

        if not in_items_area:
            continue

        qty_match = QTY_RE.match(line)
        if qty_match:
            pending_qty = {
                "quantity": euro_to_float(qty_match.group("qty")),
                "unit_price": euro_to_float(qty_match.group("unit")),
                "raw_line": line,
                "line_index": line_index,
            }
            continue



        weight_qty_match = WEIGHT_QTY_RE.match(line)
        if weight_qty_match:
            pending_qty = {
                "quantity": euro_to_float(weight_qty_match.group("weight")),
                "unit_price": euro_to_float(weight_qty_match.group("unit")),
                "unit": "kg",
                "raw_line": line,
                "line_index": line_index,
            }
            continue






        

        discount_match = DISCOUNT_RE.match(line)
        if discount_match:
            discount = {
                "line_index": line_index,
                "description_raw": discount_match.group("desc"),
                "vat_rate": vat_rate_to_int(discount_match.group("iva")),
                "amount": euro_to_float(discount_match.group("amount")),
                "raw_lines": [line],
                "applied_to_line_index": None,
            }

            if items and items[-1]["vat_rate"] == discount["vat_rate"]:
                last_item = items[-1]

                last_item["discount_amount"] = round(
                    last_item["discount_amount"] + discount["amount"],
                    2,
                )
                last_item["net_amount"] = round(
                    last_item["gross_amount"] + last_item["discount_amount"],
                    2,
                )
                last_item["raw_lines"].append(line)

                discount["applied_to_line_index"] = last_item["line_index"]
            else:
                warnings.append("sconto_non_allocato")

            discounts.append(discount)
            continue



        service_match = SERVICE_RE.match(line)
        if service_match:
            price = euro_to_float(service_match.group("price"))

            items.append(
                {
                    "line_index": line_index,
                    "description_raw": service_match.group("desc"),
                    "description_norm": None,
                    "category": None,
                    "quantity": 1.0,
                    "unit_price": None,
                    "unit": "service",
                    "gross_amount": price,
                    "discount_amount": 0.0,
                    "net_amount": price,
                    "vat_rate": None,
                    "raw_lines": [line],
                    "warnings": [],
                }
            )
            continue


        

        item_match = ITEM_RE.match(line)
        if item_match:
            price = euro_to_float(item_match.group("price"))

            item = {
                "line_index": line_index,
                "description_raw": item_match.group("desc"),
                "description_norm": None,
                "category": None,
                "quantity": 1.0,
                "unit_price": None,
                "gross_amount": price,
                "discount_amount": 0.0,
                "net_amount": price,
                "vat_rate": vat_rate_to_int(item_match.group("iva")),
                "raw_lines": [line],
                "warnings": [],
            }

            if pending_qty:
                item["line_index"] = pending_qty["line_index"]
                item["quantity"] = pending_qty["quantity"]
                item["unit_price"] = pending_qty["unit_price"]
                item["unit"] = pending_qty.get("unit", "unit")
                item["raw_lines"] = [pending_qty["raw_line"], line]
                pending_qty = None
            else:
                item["unit"] = "unit"
                
            items.append(item)
            continue

        unparsed_lines.append(line)

    if pending_qty is not None:
        warnings.append("quantita_senza_articolo_successivo")
        unparsed_lines.append(pending_qty["raw_line"])

    gross_items_total = sum(item["gross_amount"] for item in items)
    discounts_total = sum(discount["amount"] for discount in discounts)
    calculated_total = round(gross_items_total + discounts_total, 2)

    match_total = total is not None and abs(calculated_total - total) < 0.01

    if total is None:
        warnings.append("totale_mancante")

    if total is not None and not match_total:
        warnings.append("totale_non_validato")

    if any(discount["applied_to_line_index"] is None for discount in discounts):
        warnings.append("sconti_non_ancora_allocati_agli_articoli")

        
    return {
        "receipt_id": receipt_id_from_input_path(input_path),
        "source_images": source_images,
        "store": {
            "brand": metadata["negozio"]["nome"],
            "name": metadata["negozio"]["ragione_sociale"],
            "address": metadata["negozio"]["indirizzo"],
            "vat_number": metadata["negozio"]["piva"],
        },
        "datetime": split_receipt_datetime(metadata["data_ora"]),
        "document": {
            "number": metadata["numero_documento"],
        },
        "payment": metadata["pagamento"],
        "items": items,
        "discounts": discounts,
        "totals": {
            "total_amount": total,
            "vat_amount": metadata["iva_totale"],
            "gross_items_total": round(gross_items_total, 2),
            "discounts_total": round(discounts_total, 2),
            "calculated_total": calculated_total,
        },
        "validation": {
            "match_total": match_total,
        },
        "warnings": warnings,
        "unparsed_lines": unparsed_lines,
    }


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: python scripts/parse_scontrino_raw.py <trascrizione_raw.json>")
        sys.exit(1)

    input_path = Path(sys.argv[1])

    if not input_path.exists():
        print(f"File non trovato: {input_path}")
        sys.exit(1)

    data = json.loads(input_path.read_text(encoding="utf-8"))
    raw_lines = data["raw_lines"]

    parsed = parse_raw_lines(
        raw_lines,
        input_path,
        source_images=source_images_from_input(data, input_path),
    )
    PARSED_DIR.mkdir(exist_ok=True)
    output_path = PARSED_DIR / f"{output_stem_from_input_path(input_path)}.parsed.json"

    output_path.write_text(
        json.dumps(parsed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(parsed, ensure_ascii=False, indent=2))
    print(f"\nSalvato in: {output_path}")


if __name__ == "__main__":
    main()
