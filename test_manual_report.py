from pypdf import PdfReader

from models import TestControlState
from report import build_test_report


def test_manual_entries_are_written_into_their_normal_report_sections(tmp_path):
    state = TestControlState()
    state.order_no = "ORD-2026-15"
    state.project_name = "North AHU"
    state.ahu_name = "AHU-07"

    state.supply_fan_type = "EC plug fan"
    state.return_fan_type = "Danfoss exhaust fan"
    state.supply_fan_count = 2
    state.return_fan_count = 1
    state.supply_airflow = "12500"
    state.return_airflow = "10800"

    state.manual_dampers["Smoke Damper"] = 2
    state.manual_filters["F7 Bag Filter"] = "592x592, ePM1 60%"
    state.manual_modules["Plate Heat Exchanger"] = "Enabled"

    output = tmp_path / "manual-data-report.pdf"
    build_test_report(state, output)

    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(output)).pages)
    assert "ORD-2026-15" in text
    assert "North AHU" in text
    assert "AHU-07" in text
    assert "EC plug fan" in text
    assert "Danfoss exhaust fan" in text
    assert "Smoke Damper" in text
    assert "F7 Bag Filter" in text
    assert "592x592" in text
    assert "Plate Heat Exchanger" in text
    assert "Enabled" in text
    assert "Manuel" not in text


def test_manual_equipment_updates_section_statuses():
    state = TestControlState()
    assert state.damper_control_ok is False
    assert state.filter_control_ok is False
    assert state.modules_ok is False

    state.manual_dampers["Smoke Damper"] = 1
    state.manual_filters["F7 Bag Filter"] = "ePM1 60%"
    state.manual_modules["Plate Heat Exchanger"] = "Enabled"

    assert state.damper_control_ok is True
    assert state.filter_control_ok is True
    assert state.modules_ok is True



def test_report_date_and_bilingual_fan_labels_are_printed(tmp_path):
    state = TestControlState()
    state.report_date = "05.03.2026"
    state.supply_fan_type = "EC plug fan"
    state.return_fan_type = "Danfoss exhaust fan"
    state.supply_fan_count = 2
    state.return_fan_count = 1
    state.supply_airflow = "12500"
    state.return_airflow = "10800"

    output = tmp_path / "dated-bilingual-report.pdf"
    build_test_report(state, output)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(output)).pages)

    assert "05-Mar-26" in text
    assert "Ufleme Fan Tipi / Supply Fan Type" in text
    assert "Egzoz Fan Tipi / Exhaust Fan Type" in text
    assert "Ufleme Debisi (%25) / Supply Airflow" in text
    assert "Egzoz Debisi (%25) / Exhaust Airflow" in text
    assert "Ufleme Fan Adedi / Supply Fan Qty." in text
    assert "Egzoz Fan Adedi / Exhaust Fan Qty." in text


def test_invalid_manual_report_date_is_rejected(tmp_path):
    state = TestControlState()
    state.report_date = "31.02.2026"
    try:
        build_test_report(state, tmp_path / "invalid-date.pdf")
    except ValueError as exc:
        assert "GG.AA.YYYY" in str(exc)
    else:
        raise AssertionError("Invalid manual report date was accepted")



def test_unselected_electrical_heater_is_not_printed_and_selected_stages_are_bilingual(tmp_path):
    state = TestControlState()
    state.electrical_heater = False
    state.pre_electrical_heater = False
    output = tmp_path / "heater-not-selected.pdf"
    build_test_report(state, output)
    text = "\\n".join(page.extract_text() or "" for page in PdfReader(str(output)).pages)
    assert "ELECTRICAL HEATER" not in text
    assert "Elektrikli Isitici" not in text

    state.electrical_heater = True
    state.electrical_stage_count = 2
    state.electrical_values = ["10", "20", "", "", "", "", "", "", ""]
    state.pre_electrical_heater = True
    state.pre_electrical_stage_count = 1
    output = tmp_path / "heater-selected.pdf"
    build_test_report(state, output)
    text = "\\n".join(page.extract_text() or "" for page in PdfReader(str(output)).pages)
    assert "Rapor Tarihi" in text
    assert "Report Date" in text
    assert "Sayfa No" in text
    assert "Page No" in text
    assert "1. Kademe / Stage 1" in text
    assert "2. Kademe / Stage 2" in text
