"""Windows Tk geometry regression for the 400 px sensor page."""
import sys

import pytest

if sys.platform != "win32":
    pytest.skip("Pixel-accurate Tk layout is verified on the Windows build runner.", allow_module_level=True)

from app import TestControlApp as _TestControlApp


def test_sensor_page_all_rows_fit_400px():
    app = _TestControlApp()
    try:
        app.geometry("400x820")
        app.update()
        app._set_tab_visible("Sensörler", True)
        app.tabs.select(app._tab_ids["Sensörler"])
        app.update_idletasks()
        app._fit_sensor_row_widths()
        app.update_idletasks()

        measurement = app._sensor_width_measurements
        assert measurement, "Sensor layout width measurement did not run."

        available = measurement["available_px"]
        required = measurement["required_px"]
        rows = measurement["row_requested_widths_px"]
        manual_available = measurement["manual_form_available_px"]
        manual_required = measurement["manual_form_required_px"]

        print(
            "SENSOR PIXEL BUDGET: "
            f"grid={required}px/{available}px "
            f"margin={measurement['remaining_px']}px; "
            f"columns={measurement['column_minimums_px']}; "
            f"manual-form={manual_required}px/{manual_available}px "
            f"margin={measurement['manual_form_remaining_px']}px; "
            f"rows={rows}"
        )

        assert required <= available, (
            f"Sensor grid overflows by {required - available}px: "
            f"columns={measurement['column_minimums_px']}, rows={rows}"
        )
        assert manual_required <= manual_available, (
            f"Manual sensor form overflows by {manual_required - manual_available}px: "
            f"columns={measurement['manual_form_column_minimums_px']}"
        )
        assert all(width <= available for width in rows.values()), (
            f"At least one sensor row exceeds {available}px: {rows}"
        )
    finally:
        app.destroy()
