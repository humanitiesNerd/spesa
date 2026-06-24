from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
from pillow_heif import register_heif_opener
from PIL import Image
import base64
import json
import sys
import tempfile




from functools import lru_cache

from openai import OpenAI


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAI:
    return OpenAI()


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPTIONS_DIR = PROJECT_ROOT / "trascrizioni"

OCR_MODEL = "gpt-4.1-mini"

OCR_PROMPT = """
Leggi questo scontrino.

NON interpretare le righe.
NON ricostruire quantità.
NON associare righe tra loro.
NON correggere abbreviazioni.
NON trasformare lo scontrino in lista articoli.

Devi solo trascrivere il testo visibile, riga per riga, nell’ordine esatto in cui appare sullo scontrino.

Restituisci SOLO JSON valido, senza markdown.

Formato:

{
  "raw_lines": [
    "prima riga visibile",
    "seconda riga visibile",
    "terza riga visibile"
  ]
}

Regole:
- Ogni elemento di raw_lines deve corrispondere a una riga fisica dello scontrino.
- Mantieni l’ordine dall’alto verso il basso.
- Mantieni numeri, virgole, simboli %, x, EUR, asterischi e codici come li leggi.
- Non unire righe diverse.
- Non dividere una stessa riga fisica in più elementi.
- Se una riga è parzialmente illeggibile, trascrivila comunque usando "[illeggibile]" solo per la parte non leggibile.
- Non aggiungere spiegazioni.
- Non aggiungere campi oltre a raw_lines.
"""


load_dotenv(PROJECT_ROOT / ".env")
register_heif_opener()

#client = get_openai_client()


def image_to_base64_jpeg(image_path: Path) -> str:
    img = Image.open(image_path)

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        jpeg_path = Path(tmp.name)

    img.convert("RGB").save(jpeg_path, "JPEG", quality=85)

    try:
        return base64.b64encode(jpeg_path.read_bytes()).decode("utf-8")
    finally:
        jpeg_path.unlink(missing_ok=True)


def ocr_scontrino(image_path: Path) -> dict:
    client = get_openai_client()
    if not image_path.exists():
        raise FileNotFoundError(f"File non trovato: {image_path}")

    b64 = image_to_base64_jpeg(image_path)

    response = client.responses.create(
        model=OCR_MODEL,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": OCR_PROMPT,
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{b64}",
                    },
                ],
            }
        ],
    )

    raw_json = response.output_text.strip()
    data = json.loads(raw_json)

    if "raw_lines" not in data:
        raise ValueError("Risposta OCR priva del campo 'raw_lines'")

    if not isinstance(data["raw_lines"], list):
        raise ValueError("Il campo 'raw_lines' non è una lista")

    return data


def save_transcription(data: dict, image_path: Path) -> Path:
    TRANSCRIPTIONS_DIR.mkdir(exist_ok=True)

    output_path = TRANSCRIPTIONS_DIR / f"{image_path.stem}.json"
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return output_path


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: python scripts/ocr_scontrino.py <path_scontrino>")
        sys.exit(1)

    image_path = Path(sys.argv[1])

    try:
        data = ocr_scontrino(image_path)
    except Exception as exc:
        print(f"Errore: {exc}")
        sys.exit(1)

    output_path = save_transcription(data, image_path)

    print(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"\nSalvato in: {output_path}")


if __name__ == "__main__":
    main()
