from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from models import SENSOR_NAMES


SENSOR_POINTS = {
    "Fresh Air Sensor": ("FreshAirSensorMB\\TmpVal", "°C"),
    "Supply Air Sensor": ("SupplyAirSensorMB\\TmpVal", "°C"),
    "Return Air Sensor": ("ReturnAirSensorMB\\TmpVal", "°C"),
    "Exhaust Air Sensor": ("ExhaustAirSensorMB\\TmpVal", "°C"),
    "AfterCoil Air Sensor": ("AfterCoilAirSensorMB\\TmpVal", "°C"),
    "Mix Air Sensor": ("MixingAirSensorMB\\TmpVal", "°C"),
    "Room Temp Sensor 1": ("Room Temp\\Room Temp", "°C"),
    "Room Temp Sensor 2": ("Room Temp\\Room Temp", "°C"),
    "Water Temp Sensor": ("Water Temp\\Water Temp", "°C"),
    "Return CO2 Sensor": ("ReturnAirSensorMB\\CO2Val", "ppm"),
    "Return CO2 Air Sensor": ("ReturnCO2AirSensorMB\\CO2Val", "ppm"),
}

HUMIDITY_POINTS = {
    "Fresh Air Sensor": ("FreshAirSensorMB\\HumVal", "%RH"),
    "Supply Air Sensor": ("SupplyAirSensorMB\\HumVal", "%RH"),
    "Return Air Sensor": ("ReturnAirSensorMB\\HumVal", "%RH"),
    "Exhaust Air Sensor": ("ExhaustAirSensorMB\\HumVal", "%RH"),
    "AfterCoil Air Sensor": ("AfterCoilAirSensorMB\\HumVal", "%RH"),
    "Mix Air Sensor": ("MixingAirSensorMB\\HumVal", "%RH"),
}


class SensorTabMixin:
    """SENSÖRLER sekmesinin tüm UI, PDF görünürlüğü ve PLC okuma işlemleri."""

    def _add_sensors(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook)
        notebook.add(tab, text="SENSÖRLER")

        card = ttk.LabelFrame(
            body,
            text="Sensör Değerleri",
            style="Card.TLabelframe",
            padding=14,
        )
        card.pack(fill="x")

        self._sensor_vars: dict[str, tk.StringVar] = {}
        self._sensor_widgets: dict[str, tuple[ttk.Label, ttk.Entry]] = {}
        self._sensor_units: dict[str, str] = {}
        self._sensor_visibility: dict[str, dict[str, bool]] = {}

        row = 0
        for name in SENSOR_NAMES:
            label = ttk.Label(card, text=name)
            label.grid(row=row, column=0, sticky="w", pady=6, padx=(0, 20))
            var = tk.StringVar(value=self.state.sensors[name])
            self._sensor_vars[name] = var
            entry = ttk.Entry(card, textvariable=var, width=24, state="readonly")
            entry.grid(row=row, column=1, sticky="w", pady=6)
            self._sensor_widgets[name] = (label, entry)
            self._sensor_units[name] = "°C" if "CO2" not in name else "ppm"
            row += 1

        self._sensor_humidity_vars: dict[str, tk.StringVar] = {}
        self._sensor_humidity_widgets: dict[str, tuple[ttk.Label, ttk.Entry]] = {}
        for name in HUMIDITY_POINTS:
            label = ttk.Label(card, text=f"{name} Nem")
            label.grid(row=row, column=0, sticky="w", pady=6, padx=(0, 20))
            var = tk.StringVar(value="-")
            self._sensor_humidity_vars[name] = var
            entry = ttk.Entry(card, textvariable=var, width=24, state="readonly")
            entry.grid(row=row, column=1, sticky="w", pady=6)
            self._sensor_humidity_widgets[name] = (label, entry)
            row += 1

        self._sensor_save_button = ttk.Button(
            card,
            text="KAYDET",
            style="Primary.TButton",
            command=self._save,
        )
        self._sensor_save_button.grid(row=row, column=0, sticky="w", pady=(12, 0))

        self._set_sensor_visibility({name: {"temperature": False, "humidity": False, "co2": False} for name in SENSOR_NAMES})

    def _set_widget_visible(self, widgets: tuple[ttk.Label, ttk.Entry], visible: bool) -> None:
        for widget in widgets:
            if visible:
                widget.grid()
            else:
                widget.grid_remove()

    def _set_sensor_visibility(self, visibility: dict[str, dict[str, bool]]) -> None:
        for name, widgets in self._sensor_widgets.items():
            spec = visibility.get(name, {})
            self._set_widget_visible(
                widgets,
                bool(spec.get("temperature") or spec.get("co2")),
            )
        for name, widgets in self._sensor_humidity_widgets.items():
            self._set_widget_visible(widgets, bool(visibility.get(name, {}).get("humidity")))

    def _apply_pdf_sensor_visibility(self, sensor_types: dict[str, dict[str, bool]]) -> None:
        self._sensor_visibility = sensor_types
        self._set_sensor_visibility(sensor_types)
        if getattr(self, "state", None) is not None and self.state.c600_connected:
            self._read_sensors_from_plc()

    def _save_sensor_state(self) -> None:
        for name, var in self._sensor_vars.items():
            self.state.sensors[name] = var.get()
        for name, var in self._sensor_humidity_vars.items():
            self.state.sensors[f"{name} Humidity"] = var.get()

    def _clear_sensor_ui(self) -> None:
        for name, var in self._sensor_vars.items():
            var.set(self.state.sensors[name])
        for var in self._sensor_humidity_vars.values():
            var.set("-")
        self._set_sensor_visibility(
            {name: {"temperature": False, "humidity": False, "co2": False} for name in SENSOR_NAMES}
        )

    def _read_sensors_from_plc(self) -> None:
        if not self.state.c600_connected:
            return
        threading.Thread(target=self._sensor_plc_worker, daemon=True).start()

    def _sensor_plc_worker(self) -> None:
        visibility = dict(self._sensor_visibility)
        readings: list[tuple[str, str, str]] = []
        errors: list[str] = []

        for name, spec in visibility.items():
            if spec.get("temperature") and name in SENSOR_POINTS:
                point_id, unit = SENSOR_POINTS[name]
                try:
                    result = self._c600_json_read(point_id)
                    value = str(result.get("value", "")).strip() or "—"
                    readings.append(("temperature", name, f"{value} {unit}"))
                except Exception as exc:
                    errors.append(f"{name}: {exc}")
            if spec.get("co2") and name in SENSOR_POINTS:
                point_id, unit = SENSOR_POINTS[name]
                try:
                    result = self._c600_json_read(point_id)
                    value = str(result.get("value", "")).strip() or "—"
                    readings.append(("temperature", name, f"{value} {unit}"))
                except Exception as exc:
                    errors.append(f"{name}: {exc}")
            if spec.get("humidity") and name in HUMIDITY_POINTS:
                point_id, unit = HUMIDITY_POINTS[name]
                try:
                    result = self._c600_json_read(point_id)
                    value = str(result.get("value", "")).strip() or "—"
                    readings.append(("humidity", name, f"{value} {unit}"))
                except Exception as exc:
                    errors.append(f"{name} nem: {exc}")

        def apply() -> None:
            for kind, name, value in readings:
                if kind == "humidity":
                    self._sensor_humidity_vars[name].set(value)
                else:
                    self._sensor_vars[name].set(value)
                    self.state.sensors[name] = value
            if errors and hasattr(self, "_c600_log_write"):
                self._c600_log_write(f"Sensör PLC okuma hatası: {len(errors)} adet.", "error")

        self._c600_ui(apply)
