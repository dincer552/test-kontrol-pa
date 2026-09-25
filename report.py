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
    ], (52 * mm, 134 * mm)))

    # FANLAR: baslik tablo icinde, baslik hucreleri acik gri ve kalin.
    fan_rows = [
        ["FANLAR / FANS", "", "", ""],
        ["Fan Tipi / Fan Type", _value(state.fan_type),
         "Vantilator / Ventilator", "Var"],
        ["Debi Kontrol / Air Flow Control", _checked(state.airflow_control_ok),
         "Ufleme Fan Sayisi / Supply Fan Number", state.supply_fan_count],
        ["Basinc Kontrol / Pressure Control", _checked(state.pressure_control_ok),
         "Donus Fan Sayisi / Return Fan Number", state.return_fan_count],
        ["Ufleme Debi %25 / Supply Air Flow (%25)", _value(state.supply_airflow),
         "Donus Debi %25 / Return Air Flow (%25)", _value(state.return_airflow)],
    ]
    fan_table = _grid(
        fan_rows,
        (56 * mm, 37 * mm, 56 * mm, 37 * mm),
        7,
    )
    fan_table.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#eeeeee")),
        ("BACKGROUND", (2, 1), (2, -1), colors.HexColor("#eeeeee")),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 1), (2, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(fan_table)
    story.append(Spacer(1, 5 * mm))

    # MODULLER: fanlar bolumundeki sade tablo tasarimi.
    module_items = []
    if state.rotor_enabled:
        module_items.append(("Rotor", _checked(True)))
    if state.run_around:
        module_items.append(("Cevrimsel Batarya / Run Around", _checked(True)))
    if state.dx_enabled:
        module_items.append(("DX Batarya", _checked(True)))
        module_items.append(("DX Kademe Sayisi", state.dx_stage))
    if state.humidifier_enabled:
        module_items.append(("Nemlendirici", _checked(True)))
        module_items.append(("Nem. Kademe Sayisi", state.humidifier_stage))
    if state.electrical_heater:
        module_items.append(("Elektrikli Isitici", _checked(True)))
    if state.room_bms:
        module_items.append(("Room BMS", _checked(True)))

    if module_items:
        module_rows = [["MODULLER / MODULES", "", "", ""]]
        for i in range(0, len(module_items), 2):
            left = module_items[i]
            right = module_items[i + 1] if i + 1 < len(module_items) else ("", "")
            module_rows.append([left[0], left[1], right[0], right[1]])
        module_table = _grid(module_rows, (56 * mm, 37 * mm, 56 * mm, 37 * mm), 7)
        module_table.setStyle(TableStyle([
            ("SPAN", (0, 0), (-1, 0)),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#eeeeee")),
            ("BACKGROUND", (2, 1), (2, -1), colors.HexColor("#eeeeee")),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 1), (2, -1), "Helvetica-Bold"),
        ]))
        story.append(module_table)
        story.append(Spacer(1, 5 * mm))

    # DAMPERLER: sadece adedi 0'dan buyuk olanlar.
    active_dampers = []
    for name in DAMPER_NAMES:
        try:
            count = int(state.damper_counts.get(name, 0) or 0)
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            active_dampers.append((name, count))

    if active_dampers:
        damper_rows = [["DAMPERLER / DAMPERS", "", "", ""]]
        for i in range(0, len(active_dampers), 2):
            left = active_dampers[i]
            right = active_dampers[i + 1] if i + 1 < len(active_dampers) else ("", "")
            damper_rows.append([
                f"{left[0]} Damper", left[1],
                f"{right[0]} Damper" if right[0] else "",
                right[1] if right[0] else "",
            ])
        damper_table = _grid(damper_rows, (48 * mm, 48 * mm, 48 * mm, 50 * mm), 7)
        damper_table.setStyle(TableStyle([
            ("SPAN", (0, 0), (-1, 0)),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#eeeeee")),
            ("BACKGROUND", (2, 1), (2, -1), colors.HexColor("#eeeeee")),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 1), (2, -1), "Helvetica-Bold"),
        ]))
        story.append(damper_table)
        story.append(Spacer(1, 5 * mm))

    filter_rows = [["FILTRELER / FILTERS", "", "", ""]]
    filter_items = [(name, _checked(state.filters.get(name, False))) for name in FILTER_IDS]
    for i in range(0, len(filter_items), 2):
        left = filter_items[i]
        right = filter_items[i + 1] if i + 1 < len(filter_items) else ("", "")
        filter_rows.append([left[0], left[1], right[0], right[1]])
    filter_table = _grid(filter_rows, (48 * mm, 48 * mm, 48 * mm, 50 * mm), 7)
    filter_table.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#eeeeee")),
        ("BACKGROUND", (2, 1), (2, -1), colors.HexColor("#eeeeee")),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 1), (2, -1), "Helvetica-Bold"),
    ]))
    story.append(filter_table)
    story.append(Spacer(1, 5 * mm))

    story.append(PageBreak())
    story.extend([_header_table(styles, "2/2", now), Spacer(1, 4)])
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
    # Degeri olmayan sensörleri raporda gosterme.
    sensor_rows = []
    for name, label in sensor_labels:
        if name not in SENSOR_NAMES:
            continue
        value = _value(state.sensors.get(name, "-"))
        if value != "-":
            sensor_rows.append([label, value])
    for name, value in state.manual_sensors.items():
        value_text = _value(value)
        if value_text != "-":
            sensor_rows.append([f"Manuel / {name}", value_text])
    half = (len(sensor_rows) + 1) // 2
    left, right = sensor_rows[:half], sensor_rows[half:]
    while len(right) < len(left):
        right.append(["", ""])
    sensor_rows_table = [["SENSORLER / SENSORS", "", "", ""]]
    sensor_rows_table.extend([[a, b, c, d] for (a, b), (c, d) in zip(left, right)])
    sensor_table = _grid(sensor_rows_table, (49 * mm, 47 * mm, 49 * mm, 47 * mm), 7)
    sensor_table.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#eeeeee")),
        ("BACKGROUND", (2, 1), (2, -1), colors.HexColor("#eeeeee")),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 1), (2, -1), "Helvetica-Bold"),
    ]))
    story.append(sensor_table)

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
    heater = [["ELEKTRIKLI ISITICI / ELECTRICAL HEATER", "", "", ""], *heater]
    ht = _grid(heater, (42 * mm, 24 * mm, 24 * mm, 24 * mm), 7)
    ht.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BACKGROUND", (0, 2), (0, -1), colors.HexColor("#eeeeee")),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("ALIGN", (1, 2), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (-1, 1), "CENTER"),
    ]))
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
