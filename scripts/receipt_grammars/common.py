import re

PRICE_RE = r"\d+,\d{2}"
UNIT_PRICE_RE = r"\d+,\d{2,3}"
VAT_RE = r"\d+(?:,\d)?%"
DISCOUNT_AMOUNT_RE = rf"-{PRICE_RE}"

TOTAL_RE = re.compile(rf"^TOTALE COMPLESSIVO\s+(?P<total>{PRICE_RE})$")
IVA_TOTAL_RE = re.compile(rf"^di cui IVA\s+(?P<iva>{PRICE_RE})$")
PAYMENT_RE = re.compile(rf"^Pagamento\s+(?P<method>.+?)\s+(?P<amount>{PRICE_RE})$")
DOCUMENT_RE = re.compile(r"^DOCUMENTO N\.\s*(?P<number>.+)$", re.IGNORECASE)
DATETIME_RE = re.compile(r"^(?P<date>\d{2}-\d{2}-\d{4})\s+(?P<time>\d{2}:\d{2})$")




PIVA_RE = re.compile(
    r"\b(?:P\.?\s*IVA|PI|PARTITA\s+IVA)\s*[:\-]?\s*(?P<piva>\d{11})\b",
    re.IGNORECASE,
)



WEIGHT_QTY_RE = re.compile(
    rf"^(?P<weight>\d+,\d{{3}})\s*kg\s*x\s*(?P<unit>{UNIT_PRICE_RE})\s*EUR/kg$",
    re.IGNORECASE,
)

SERVICE_RE = re.compile(
    rf"^(?P<desc>CONSEGNA DOMICILIO)\s+NS\*\s+(?P<price>{PRICE_RE})$"
)
