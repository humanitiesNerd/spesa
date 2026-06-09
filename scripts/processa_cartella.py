from pathlib import Path
import sys

from scripts.processa_scontrino import processa_scontrino
from scripts.parse_scontrino_raw import PARSED_DIR


SUPPORTED_EXTENSIONS = {".heic", ".heif", ".jpg", ".jpeg", ".png"}


def is_supported_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


def parsed_output_path(image_path: Path) -> Path:
    return PARSED_DIR / f"{image_path.stem}.parsed.json"


def processa_cartella(input_dir: Path) -> dict:
    if not input_dir.exists():
        raise FileNotFoundError(f"Cartella non trovata: {input_dir}")

    if not input_dir.is_dir():
        raise NotADirectoryError(f"Non è una cartella: {input_dir}")

    images = sorted(
        path
        for path in input_dir.iterdir()
        if is_supported_image(path)
    )

    results = {
        "processati": [],
        "saltati": [],
        "falliti": [],
    }

    for image_path in images:
        output_path = parsed_output_path(image_path)

        if output_path.exists():
            results["saltati"].append(str(image_path))
            print(f"SKIP  {image_path} -> già parsato")
            continue

        try:
            print(f"OCR   {image_path}")
            result = processa_scontrino(image_path)

            results["processati"].append({
                "input": str(image_path),
                "ocr": str(result["transcription_path"]),
                "parsed": str(result["parsed_path"]),
                "match_totale": result["parsed"]["validation"]["match_total"],
            })

            print(f"OK    {image_path}")

        except Exception as exc:
            results["falliti"].append({
                "input": str(image_path),
                "errore": str(exc),
            })

            print(f"FAIL  {image_path}: {exc}")

    return results


def print_summary(results: dict) -> None:
    print()
    print("Riepilogo")
    print("---------")
    print(f"Processati: {len(results['processati'])}")
    print(f"Saltati:    {len(results['saltati'])}")
    print(f"Falliti:    {len(results['falliti'])}")

    failed_total = [
        item
        for item in results["processati"]
        if item["match_totale"] is False
    ]

    if failed_total:
        print()
        print("Attenzione: scontrini processati ma con totale non validato:")
        for item in failed_total:
            print(f"- {item['input']}")


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: python -m scripts.processa_cartella <cartella_scontrini>")
        sys.exit(1)

    input_dir = Path(sys.argv[1])

    try:
        results = processa_cartella(input_dir)
    except Exception as exc:
        print(f"Errore: {exc}")
        sys.exit(1)

    print_summary(results)


if __name__ == "__main__":
    main()
