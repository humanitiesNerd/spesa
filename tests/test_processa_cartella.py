from pathlib import Path

import pytest

from scripts.processa_cartella import processa_cartella


def test_processa_cartella_processes_supported_images(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    parsed_dir = tmp_path / "parsed_receipts"
    input_dir.mkdir()
    parsed_dir.mkdir()

    image_path = input_dir / "20260529_120000.heic"
    image_path.write_bytes(b"fake image")

    def fake_processa_scontrino(path: Path) -> dict:
        return {
            "transcription_path": tmp_path / f"{path.stem}.json",
            "parsed_path": parsed_dir / f"{path.stem}.parsed.json",
            "parsed": {
                "validation": {
                    "match_total": True,
                },
            },
        }

    monkeypatch.setattr(
        "scripts.processa_cartella.PARSED_DIR",
        parsed_dir,
    )
    monkeypatch.setattr(
        "scripts.processa_cartella.processa_scontrino",
        fake_processa_scontrino,
    )

    results = processa_cartella(input_dir)

    assert len(results["processati"]) == 1
    assert results["processati"][0]["input"] == str(image_path)
    assert results["processati"][0]["match_totale"] is True
    assert results["saltati"] == []
    assert results["falliti"] == []


def test_processa_cartella_skips_already_parsed_images(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    parsed_dir = tmp_path / "parsed_receipts"
    input_dir.mkdir()
    parsed_dir.mkdir()

    image_path = input_dir / "20260529_120000.heic"
    image_path.write_bytes(b"fake image")

    existing_output = parsed_dir / "20260529_120000.parsed.json"
    existing_output.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        "scripts.processa_cartella.PARSED_DIR",
        parsed_dir,
    )

    results = processa_cartella(input_dir)

    assert results["processati"] == []
    assert results["saltati"] == [str(image_path)]
    assert results["falliti"] == []


def test_processa_cartella_ignores_unsupported_files(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    parsed_dir = tmp_path / "parsed_receipts"
    input_dir.mkdir()
    parsed_dir.mkdir()

    unsupported_file = input_dir / "notes.txt"
    unsupported_file.write_text("not an image", encoding="utf-8")

    monkeypatch.setattr(
        "scripts.processa_cartella.PARSED_DIR",
        parsed_dir,
    )

    results = processa_cartella(input_dir)

    assert results == {
        "processati": [],
        "saltati": [],
        "falliti": [],
    }


def test_processa_cartella_records_failures(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    parsed_dir = tmp_path / "parsed_receipts"
    input_dir.mkdir()
    parsed_dir.mkdir()

    image_path = input_dir / "20260529_120000.jpg"
    image_path.write_bytes(b"fake image")

    def fake_processa_scontrino(path: Path) -> dict:
        raise RuntimeError("fake OCR failure")

    monkeypatch.setattr(
        "scripts.processa_cartella.PARSED_DIR",
        parsed_dir,
    )
    monkeypatch.setattr(
        "scripts.processa_cartella.processa_scontrino",
        fake_processa_scontrino,
    )

    results = processa_cartella(input_dir)

    assert results["processati"] == []
    assert results["saltati"] == []
    assert len(results["falliti"]) == 1
    assert results["falliti"][0]["input"] == str(image_path)
    assert results["falliti"][0]["errore"] == "fake OCR failure"


def test_processa_cartella_requires_existing_directory(tmp_path):
    missing_dir = tmp_path / "missing"

    with pytest.raises(FileNotFoundError):
        processa_cartella(missing_dir)


def test_processa_cartella_requires_directory(tmp_path):
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("not a directory", encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        processa_cartella(not_a_dir)
