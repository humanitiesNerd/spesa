import re

DOK_INFO_LINE_RE = re.compile(
    r"^(Taglio Prezzo Fidelity|Off T\.P\. Carta Club)$",
    re.IGNORECASE,
)
