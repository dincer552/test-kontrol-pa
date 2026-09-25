from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from tkinter import filedialog

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from models import DAMPER_NAMES, FILTER_IDS, SENSOR_NAMES, TestControlState


def _asset_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def _value(value: object) -> str:
    text = _ascii(str(value).strip())
    return text if text and text != "-" else "-"


def _ascii(text: str) -> str:
    """Keep the PDF compatible with the built-in Helvetica font."""
    return str(text).translate(str.maketrans({
        "ç": "c", "Ç": "C", "ğ": "g", "Ğ": "G",
        "ı": "i", "İ": "I", "ö": "o", "Ö": "O",
        "ş": "s", "Ş": "S", "ü": "u", "Ü": "U",
    }))


def _checked(value: bool) -> str:
    return "Checked" if value else "-"


def _sensor_value(state: TestControlState, name: str) -> str:
    return _value(state.sensors.get(name, "-"))


def _header_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.drawString(15 * mm, 8 * mm, _ascii("Systemair HSK Havalandırma Endüstri San. Ve Tic. A. Ş."))
    canvas.drawRightString(195 * mm, 8 * mm, _ascii(f"Sayfa {doc.page}"))
    canvas.restoreState()


def _grid(rows, widths, font_size=7.5) -> Table:
    rows = [[_ascii(str(cell)) for cell in row] for row in rows]
    table = Table(rows, colWidths=widths)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _header_table(styles, page_no: str, updated: str) -> Table:
    logo_path = _asset_path("SYSR.ST.png")
    logo = Image(str(logo_path), width=28 * mm, height=20 * mm, kind="proportional") if logo_path.exists() else Paragraph("systemair", styles["title"])
    meta = [
        ["Doküman No", "Form-550"],
        ["Yayın Tarihi", "10/10/2025"],
        ["Rev. No/Tarih", "00/00.00.0000"],
        ["Güncelleme Tarihi", updated],
        ["Sayfa No", page_no],
    ]
    meta_table = _grid(meta, (29 * mm, 31 * mm), 6.5)
    title = Paragraph(
        "OTOMASYON TEST RAPORU<br/><font size='9'>AUTOMATION TEST REPORT</font>",
        styles["title"],
    )
    header = Table([[logo, title, meta_table]], colWidths=[42 * mm, 92 * mm, 60 * mm])
    header.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (1, 0), 5),
        ("RIGHTPADDING", (0, 0), (1, 0), 5),
        # Sagdaki Dokuman No tablosu kendi hucre sinirlarinin disina tasmasin.
        ("LEFTPADDING", (2, 0), (2, 0), 0),
        ("RIGHTPADDING", (2, 0), (2, 0), 0),
    ]))
    return header


def build_test_report(state: TestControlState, output_path: str | os.PathLike[str]) -> str:
    output = str(output_path)
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        title="OTOMASYON TEST RAPORU / AUTOMATION TEST REPORT",
        author=state.user_name or "TEST KONTROL",
    )
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("report_title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=13, leading=15, alignment=TA_CENTER),
        "section": ParagraphStyle("report_section", parent=base["Heading4"], fontName="Helvetica-Bold", fontSize=9, leading=11, spaceBefore=6, spaceAfter=4),
        "small": ParagraphStyle("report_small", parent=base["Normal"], fontName="Helvetica", fontSize=7, leading=8),
        "small_bold": ParagraphStyle("report_small_bold", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7, leading=8),
    }

    now = datetime.now().strftime("%d-%b-%y %H:%M:%S")
    story = [_header_table(styles, "1/2", now), Spacer(1, 4)]
    story.append(Paragraph(_ascii(f"PROJE / PROJECT &nbsp;&nbsp;&nbsp; Tarih/Date: <b>{now}</b>"), styles["small_bold"]))
    story.append(_grid([
        ["Sipariş No / Order No", _value(state.order_no)],
        ["Proje Adı / Project Name", _value(state.project_name)],
        ["AHU Adı / AHU Name", _value(state.ahu_name)],
    ], (52 * mm, 142 * mm)))

    story.append(Paragraph("FANLAR / FANS", styles["section"]))
    story.append(_grid([
        ["Fan Tipi / Fan Type", _value(state.fan_type), "Üfleme Fan Sayısı / Supply Fan Number", state.supply_fan_count],
        ["Debi Kontrol / Air Flow Control", _checked(state.airflow_control_ok), "Dönüş Fan Sayısı / Return Fan Number", state.return_fan_count],
        ["Basınç Kontrol / Pressure Control", _checked(state.pressure_control_ok), "Üfleme Debi %25 / Supply Air Flow (%25)", _value(state.supply_airflow)],
        ["", "", "Dönüş Debi %25 / Return Air Flow (%25)", _value(state.return_airflow)],
    ], (43 * mm, 48 * mm, 55 * mm, 48 * mm)))

    story.append(Paragraph("MODULLER / MODULES", styles["section"]))
    module_items = [
        ("Rotor", _checked(state.rotor_enabled)),
        ("Cevrimsel Batarya / Run Around", _checked(state.run_around)),
        ("DX Batarya", _checked(state.dx_enabled)),
        ("Nemlendirici", _checked(state.humidifier_enabled)),
        ("Elektrikli Isitici", _checked(state.electrical_heater)),
        ("Room BMS", _checked(state.room_bms)),
        ("DX Kademe Sayisi", state.dx_stage if state.dx_enabled else "-"),
        ("Nem. Kademe Sayisi", state.humidifier_stage if state.humidifier_enabled else "-"),
    ]
    story.append(_grid(
        [[a, b, c, d] for (a, b), (c, d) in zip(module_items[::2], module_items[1::2])],
        (48 * mm, 48 * mm, 48 * mm, 50 * mm),
    ))

    story.append(Paragraph("DAMPERLER / DAMPERS", styles["section"]))
    damper_rows = []
    for left, right in zip(DAMPER_NAMES[::2], DAMPER_NAMES[1::2]):
        damper_rows.append([
            f"{left} Damper", state.damper_counts.get(left, 0),
            f"{right} Damper", state.damper_counts.get(right, 0),
        ])
    story.append(_grid(damper_rows, (48 * mm, 48 * mm, 48 * mm, 50 * mm)))

    story.append(Paragraph("FILTRELER / FILTERS", styles["section"]))
    story.append(Paragraph(_ascii(
        " &nbsp;&nbsp; ".join(f"{name}: {_checked(state.filters.get(name, False))}" for name in FILTER_IDS),
    ), styles["small"]))

    story.append(PageBreak())
    story.extend([_header_table(styles, "2/2", now), Spacer(1, 4)])
    story.append(Paragraph(_ascii(f"SENSORLER / SENSORS &nbsp;&nbsp;&nbsp; Tarih/Date: <b>{now}</b>"), styles["small_bold"]))

    sensor_labels = [
        ("Fresh Air Sensor", "Fresh Air Temp. Sensor"),
        ("Supply Air Sensor", "Supply Air Temp. Sensor"),
        ("Return Air Sensor", "Return Air Temp. Sensor"),
        ("Exhaust Air Sensor", "Exhaust Air Temp. Sensor"),
        ("AfterCoil Air Sensor", "AfterCoil Air Temp. Sensor"),
        ("Mix Air Sensor", "Mix Air Temp. Sensor"),
        ("AfterDxUnit Air Sensor", "AfterDxUnit Air Temp. Sensor"),
        ("AfterHeatRec Air Sensor", "AfterHeatRec Air Temp. Sensor"),
        ("Exchngr Leave Temp Sensor", "Exchngr Leave Temp Sensor"),
        ("Room Temp Sensor 1", "Room Temp Sensor"),
        ("Room Temp Sensor 2", "Room Temp Sensor 2"),
        ("Water Temp Sensor", "Water Temp Sensor"),
        ("Room CO2 Sensor", "Room CO2 Sensor"),
        ("Room Hum Sensor", "Room Hum Sensor"),
        ("Return CO2 Sensor", "Return CO2 Sensor"),
        ("Return CO2 Air Sensor", "Return Air CO2 Temp. Sensor"),
    ]
    sensor_rows = [[label, _sensor_value(state, name)] for name, label in sensor_labels if name in SENSOR_NAMES]
    sensor_rows.extend([[f"Manuel / {name}", _value(value)] for name, value in state.manual_sensors.items()])
    half = (len(sensor_rows) + 1) // 2
    left, right = sensor_rows[:half], sensor_rows[half:]
    while len(right) < len(left):
        right.append(["", ""])
    story.append(_grid(
        [[a, b, c, d] for (a, b), (c, d) in zip(left, right)],
        (49 * mm, 47 * mm, 49 * mm, 47 * mm),
    ))

    story.append(Paragraph("ELEKTRIKLI ISITICI / ELECTRICAL HEATER", styles["section"]))
    heater = [["Electrical Heater", "R(A)", "S(A)", "T(A)"]]
    stage_count = max(1, min(3, int(state.electrical_stage_count or 1)))
    for stage in range(stage_count):
        stage_number = stage + 1
        heater.append([
            f"{stage_number}.Kademe",
            _value(state.electrical_values[stage]),
            _value(state.electrical_values[3 + stage]),
            _value(state.electrical_values[6 + stage]),
        ])
    ht = _grid(heater, (42 * mm, 24 * mm, 24 * mm, 24 * mm))
    ht.setStyle(TableStyle([("ALIGN", (1, 0), (-1, -1), "CENTER"), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]))
    story.append(ht)

    story.extend([
        Spacer(1, 10),
        Paragraph(f"<b>Hazirlayan / Prepared by:</b> {_value(state.user_name)}", styles["small"]),
        Paragraph(f"<b>Not / Note:</b> {_value(state.notlar)}", styles["small"]),
    ])
    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return output


def save_report_dialog(
    parent,
    state: TestControlState,
    initial_dir: str | os.PathLike[str] | None = None,
) -> str | None:
    default_name = state.ahu_name.strip() or state.project_name.strip() or "Test_Raporu"
    safe = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in default_name)

    options = {
        "parent": parent,
        "title": "Test Raporunu Kaydet",
        "defaultextension": ".pdf",
        "initialfile": f"{safe}_Test_Raporu.pdf",
        "filetypes": [("PDF dosyası", "*.pdf")],
    }
    if initial_dir:
        try:
            initial_path = Path(initial_dir)
            if initial_path.is_dir():
                options["initialdir"] = str(initial_path)
        except (OSError, TypeError, ValueError):
            pass

    path = filedialog.asksaveasfilename(**options)
    if not path:
        return None
    return build_test_report(state, path)
