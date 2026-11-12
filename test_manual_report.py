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
