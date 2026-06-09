from pathlib import Path
import json
import sys

from scripts.ocr_scontrino import ocr_scontrino, save_transcription
from scripts.parse_scontrino_raw import (
    parse_raw_lines,
    PARSED_DIR,
)


def save_parsed(data: dict, image_path: Path) -> Path:
    PARSED_DIR.mkdir(exist_ok=True)

    output_path = PARSED_DIR / f"{image_path.stem}.parsed.json"

    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return output_path


def processa_scontrino(image_path: Path) -> dict:
    raw_data = ocr_scontrino(image_path)

    transcription_path = save_transcription(raw_data, image_path)

    parsed_data = parse_raw_lines(raw_data["raw_lines"], transcription_path)

    parsed_path = save_parsed(parsed_data, image_path)

    return {
        "ocr": raw_data,
        "parsed": parsed_data,
        "transcription_path": transcription_path,
        "parsed_path": parsed_path,
    }


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: python scripts/processa_scontrino.py <path_scontrino>")
        sys.exit(1)

    image_path = Path(sys.argv[1])

    try:
        result = processa_scontrino(image_path)
    except Exception as exc:
        print(f"Errore: {exc}")
        sys.exit(1)

    print(json.dumps(result["parsed"], ensure_ascii=False, indent=2))

    print(f"\nOCR salvato in: {result['transcription_path']}")
    print(f"Parsed salvato in: {result['parsed_path']}")


if __name__ == "__main__":
    main()
