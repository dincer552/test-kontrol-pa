"""Windows UI regression tests for removing manually entered records and overrides."""
import sys
import tkinter.ttk as ttk

import pytest

if sys.platform != "win32":
    pytest.skip("Manual-entry UI controls are verified on the Windows build runner.", allow_module_level=True)

from app import TestControlApp


def test_manual_entries_can_be_deleted_individually_from_all_sections():
    app = TestControlApp()
    try:
        # Project fields
        app._order_no_var.set("ORD-1")
        app.state.order_no = "ORD-1"
        app._clear_project_field("order_no")
        assert app._order_no_var.get() == ""
        assert app.state.order_no == ""

        # Fan values and airflow overrides
        app._aspirator_fan_type_var.set("Ziehl-Abegg")
        app._aspirator_fan_count_var.set("2")
        app._ventilator_fan_type_var.set("ebm-papst")
        app._ventilator_fan_count_var.set("1")
        app.state.return_fan_type = "Ziehl-Abegg"
        app.state.supply_fan_type = "ebm-papst"
        app._clear_manual_fan_info()
        assert app._aspirator_fan_type_var.get() == "Yok"
        assert app._aspirator_fan_count_var.get() == "0"
        assert app.state.return_fan_type == ""
        assert app.state.supply_fan_type == ""

        app._supply_airflow_var.set("12000")
        app.state.supply_airflow = "12000"
        app._supply_airflow_entry.configure(state="normal")
        app._clear_manual_airflow("supply")
        assert app._supply_airflow_var.get() == ""
        assert app.state.supply_airflow == ""
        assert str(app._supply_airflow_entry.cget("state")) == "readonly"

        # Predefined damper manual override and separately added damper
        app._damper_vars["Fresh"].set("3")
        app.state.damper_counts["Fresh"] = 3
        app._damper_widgets["Fresh"][1].configure(state="normal")
        app._clear_damper_value("Fresh")
        assert app._damper_vars["Fresh"].get() == "0"
        assert app.state.damper_counts["Fresh"] == 0

        app.state.manual_dampers["Smoke Damper"] = 2
        app._render_manual_dampers()
        app._delete_manual_damper("Smoke Damper")
        assert "Smoke Damper" not in app.state.manual_dampers

        # Additional filters and modules
        app.state.manual_filters["F7 Filter"] = "ePM1 60%"
        app._render_manual_filters()
        app._delete_manual_filter("F7 Filter")
        assert "F7 Filter" not in app.state.manual_filters

        app.state.manual_modules["Plate Heat Exchanger"] = "Enabled"
        app._render_manual_modules()
        app._delete_manual_module("Plate Heat Exchanger")
        assert "Plate Heat Exchanger" not in app.state.manual_modules

        # Manually added sensor and manual overrides of standard sensors
        app._manual_sensor_name_var.set("Outdoor Humidity Probe")
        app._manual_sensor_value_var.set("55")
        app._manual_sensor_unit_var.set("%RH")
        app._add_manual_sensor()
        assert "Outdoor Humidity Probe" in app.state.manual_sensors
        app._delete_manual_sensor("Outdoor Humidity Probe")
        assert "Outdoor Humidity Probe" not in app.state.manual_sensors
        assert "Outdoor Humidity Probe" not in app.state.manual_sensor_units

        app._sensor_vars["Fresh Air Sensor"].set("21.5")
        app._clear_sensor_value("Fresh Air Sensor")
        assert app._sensor_vars["Fresh Air Sensor"].get() == "-"
        assert app.state.sensors["Fresh Air Sensor"] == "-"

        app._sensor_humidity_vars["Supply Air Sensor"].set("45")
        app._clear_sensor_value("Supply Air Sensor", humidity=True)
        assert app._sensor_humidity_vars["Supply Air Sensor"].get() == "-"
        assert app.state.sensors["Supply Air Sensor Humidity"] == "-"

        # Module heater current values can be cleared per phase
        app._heater_table_values["electrical"][("R", 1)].set("12.5")
        app._clear_heater_phase("electrical", "R")
        assert app._heater_table_values["electrical"][("R", 1)].get() == ""

        # Report identity and date fields
        app._user_var.set("Test User")
        app._report_date_var.set("12.11.2026")
        app._clear_report_field("user")
        app._clear_report_field("date")
        assert app._user_var.get() == ""
        assert app._report_date_var.get() == ""
        assert str(app._report_date_entry.cget("state")) == "readonly"
    finally:
        app.destroy()


def test_manual_list_rows_expose_a_sil_button():
    app = TestControlApp()
    try:
        app.state.manual_dampers["Smoke Damper"] = 1
        app._render_manual_dampers()
        app.state.manual_filters["F7 Filter"] = "ePM1 60%"
        app._render_manual_filters()
        app.state.manual_modules["Plate Heat Exchanger"] = "Enabled"
        app._render_manual_modules()

        for frame in (
            app._manual_damper_list,
            app._manual_filter_list,
            app._manual_module_list,
        ):
            assert any(
                isinstance(widget, ttk.Button)
                and widget.cget("text") == "Sil"
                for widget in frame.winfo_children()
            )
    finally:
        app.destroy()
