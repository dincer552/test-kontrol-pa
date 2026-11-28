from __future__ import annotations

from pathlib import Path

import pytest
import pymupdf as fitz

from io_discovery import discover_pol648_connections, _ocr_page


def _make_vector_project(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)

    # POL648 terminal and its drawn vertical conductor.
    page.insert_text((94, 58), "X1", fontsize=11)
    page.draw_line((100, 72), (100, 330), color=(0, 0, 0), width=0.8)

    # Cable reference and signal label printed along the conductor.
    page.insert_text((94, 112), "31", fontsize=8, color=(0.8, 0.1, 0.1))
    page.insert_text((108, 180), "DI_Pres_SW_1", fontsize=10, rotate=90)
    doc.save(path)
    doc.close()


def test_vector_text_and_wire_geometry_find_connected_terminal(tmp_path: Path) -> None:
    pdf_path = tmp_path / "pol648-vector.pdf"
    _make_vector_project(pdf_path)

    diagnostics: dict = {}
    results = discover_pol648_connections(
        pdf_path, enable_ocr=False, diagnostics=diagnostics
    )

    assert diagnostics["pages_scanned"] == 1
    assert results
    row = next(item for item in results if item.terminal == "X1")
    assert row.signal == "Pres_SW_1"
    assert row.signal_type == "DI"
    assert row.cable == "31"
    assert row.page == 1


def test_scanned_page_can_be_read_by_rapidocr_when_installed(tmp_path: Path) -> None:
    Image = pytest.importorskip("PIL.Image")
    ImageDraw = pytest.importorskip("PIL.ImageDraw")
    ImageFont = pytest.importorskip("PIL.ImageFont")
    pytest.importorskip("rapidocr")
    import io

    image = Image.new("RGB", (1200, 500), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=42)
    draw.text((90, 35), "X1", fill="black", font=font)
    draw.line((120, 110, 120, 460), fill="black", width=4)
    draw.text((150, 190), "DI EMERGENCY STOP", fill="black", font=font)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    doc = fitz.open()
    page = doc.new_page(width=600, height=250)
    page.insert_image(page.rect, stream=buffer.getvalue())
    pdf_path = tmp_path / "pol648-scanned.pdf"
    doc.save(pdf_path)
    doc.close()

    scanned_doc = fitz.open(pdf_path)
    try:
        items = _ocr_page(scanned_doc[0], dpi=220)
    finally:
        scanned_doc.close()

    assert items
    assert any("X1" in item.text.upper() or "EMERGENCY" in item.text.upper() for item in items)



def test_adjacent_terminals_in_one_cad_text_span_keep_separate_coordinates(tmp_path: Path) -> None:
    pdf_path = tmp_path / "pol648-multiple-pins.pdf"
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)

    # CAD exporters commonly store a whole terminal row in one text span.
    page.insert_text((50, 60), "X1 M X2", fontsize=14)
    page.draw_line((58, 72), (58, 330), color=(0, 0, 0), width=0.8)
    page.draw_line((84, 72), (84, 330), color=(0, 0, 0), width=0.8)
    page.insert_text((65, 180), "DI_FIRE_ALARM", fontsize=10, rotate=90)
    page.insert_text((91, 180), "AI_SUPPLY_TEMP", fontsize=10, rotate=90)
    doc.save(pdf_path)
    doc.close()

    rows = discover_pol648_connections(pdf_path, enable_ocr=False)
    by_terminal = {row.terminal: row for row in rows}

    assert by_terminal["X1"].signal == "FIRE_ALARM"
    assert by_terminal["X1"].signal_type == "DI"
    assert by_terminal["X2"].signal == "SUPPLY_TEMP"
    assert by_terminal["X2"].signal_type == "AI"
