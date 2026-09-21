from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from models import SENSOR_NAMES


SENSOR_POINTS = {
    "Fresh Air Sensor": ("5-TMPVAL", "°C"),
    "Supply Air Sensor": ("SUPPLY_AIR_TEMP", "°C"),
    "Return Air Sensor": ("3-TMPVAL", "°C"),
    "Exhaust Air Sensor": ("TMPVAL", "°C"),
    "AfterCoil Air Sensor": ("1-TMPVAL", "°C"),
    "Mix Air Sensor": ("7-TMPVAL", "°C"),
    "Room Temp Sensor 1": ("ROOM_TEMP", "°C"),
    "AfterDxUnit Air Sensor": ("2-TMPVAL", "°C"),
    "AfterHeatRec Air Sensor": ("4-TMPVAL", "°C"),
    "Exchngr Leave Temp Sensor": ("6-TMPVAL", "°C"),
}

HUMIDITY_POINTS = {
    "Supply Air Sensor": ("1-HUMVAL", "%RH"),
    "Return Air Sensor": ("HUMVAL", "%RH"),
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
        self._sensor_card = card

        self._sensor_vars: dict[str, tk.StringVar] = {}
        self._sensor_widgets: dict[str, tuple[ttk.Label, ttk.Entry]] = {}
        self._sensor_manual_buttons: dict[str, ttk.Button] = {}
        self._sensor_units: dict[str, str] = {}
        self._sensor_visibility: dict[str, dict[str, bool]] = {}
        self._manual_sensor_rows: dict[str, tuple[ttk.Label, ttk.Entry]] = {}

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
            button = ttk.Button(
                card,
                text="MANUEL GİRİŞ",
                style="Secondary.TButton",
                command=lambda sensor_name=name: self._toggle_sensor_manual(sensor_name),
            )
            button.grid(row=row, column=2, sticky="w", padx=(8, 0), pady=6)
            self._sensor_manual_buttons[name] = button
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

        self._sensor_read_button = ttk.Button(
            card,
            text="VERİLERİ ÇEK",
            style="Primary.TButton",
            command=self._read_sensors_from_plc,
        )
        self._sensor_read_button.grid(row=row, column=0, sticky="w", pady=(12, 0), padx=(0, 8))

        self._sensor_save_button = ttk.Button(
            card,
            text="KAYDET",
            style="Primary.TButton",
            command=lambda: self._save_and_unlock("USER / RAPOR"),
        )
        self._sensor_save_button.grid(row=row, column=1, sticky="w", pady=(12, 0))

        row += 1
        manual_card = ttk.LabelFrame(
            card, text="Manuel Sensör Ekle", style="Card.TLabelframe", padding=10
        )
        manual_card.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Label(manual_card, text="Sensör Adı").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._manual_sensor_name_var = tk.StringVar()
        ttk.Entry(manual_card, textvariable=self._manual_sensor_name_var, width=28).grid(
            row=0, column=1, sticky="w", padx=(0, 10)
        )
        ttk.Label(manual_card, text="Değer").grid(row=0, column=2, sticky="w", padx=(0, 8))
        self._manual_sensor_value_var = tk.StringVar()
        ttk.Entry(
            manual_card, textvariable=self._manual_sensor_value_var, width=16, style="Green.TEntry"
        ).grid(row=0, column=3, sticky="w", padx=(0, 10))
        ttk.Button(
            manual_card, text="+ SENSOR EKLE", style="Secondary.TButton",
            command=self._add_manual_sensor,
        ).grid(row=0, column=4, sticky="w")

        self._set_sensor_visibility({name: {"temperature": False, "humidity": False, "co2": False} for name in SENSOR_NAMES})

    def _toggle_sensor_manual(self, name: str) -> None:
        entry = self._sensor_widgets[name][1]
        button = self._sensor_manual_buttons[name]
        if str(entry.cget("state")) == "readonly":
            entry.configure(state="normal", style="Green.TEntry")
            button.configure(text="PLC OKU")
            if hasattr(self, "_log"):
                self._log(f"SENSÖRLER: {name} manuel değer girişi açıldı.")
        else:
            entry.configure(state="readonly", style="TEntry")
            button.configure(text="MANUEL GİRİŞ")
            self.state.sensors[name] = self._sensor_vars[name].get()
            if hasattr(self, "_log"):
                self._log(f"SENSÖRLER: {name} manuel değer = {self._sensor_vars[name].get()}", "ok")

    def _add_manual_sensor(self) -> None:
        name = self._manual_sensor_name_var.get().strip()
        value = self._manual_sensor_value_var.get().strip()
        if not name or not value:
            return
        if name in self._sensor_vars or name in self._manual_sensor_rows:
            return

        row = len(self._sensor_vars) + len(self._sensor_humidity_vars) + len(self._manual_sensor_rows) + 1
        label = ttk.Label(self._sensor_card, text=name)
        label.grid(row=row, column=0, sticky="w", pady=6, padx=(0, 20))
        entry = ttk.Entry(self._sensor_card, width=24, style="Green.TEntry")
        entry.insert(0, value)
        entry.grid(row=row, column=1, sticky="w", pady=6)
        self._manual_sensor_rows[name] = (label, entry)
        self.state.manual_sensors[name] = value
        self._manual_sensor_name_var.set("")
        self._manual_sensor_value_var.set("")
        if hasattr(self, "_log"):
            self._log(f"SENSÖRLER: Manuel sensör eklendi — {name} = {value}", "ok")

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
        for name, (_label, entry) in self._manual_sensor_rows.items():
            self.state.manual_sensors[name] = entry.get()

    def _clear_sensor_ui(self) -> None:
        for name, var in self._sensor_vars.items():
            var.set(self.state.sensors[name])
        for var in self._sensor_humidity_vars.values():
            var.set("-")
        for label, entry in self._manual_sensor_rows.values():
            label.destroy()
            entry.destroy()
        self._manual_sensor_rows.clear()
        self.state.manual_sensors.clear()
        self._set_sensor_visibility(
            {name: {"temperature": False, "humidity": False, "co2": False} for name in SENSOR_NAMES}
        )

    def _read_sensors_from_plc(self) -> None:
        if not self.state.c600_connected:
            if hasattr(self, "_log"):
                self._log("SENSÖRLER: Veri çekme isteği reddedildi; C600 bağlı değil.", "error")
            return
        if hasattr(self, "_log"):
            self._log("SENSÖRLER: Görünür sensör verileri PLC'den okunuyor...")
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
            if hasattr(self, "_log"):
                for kind, name, value in readings:
                    self._log(f"SENSÖRLER: {name} [{kind}] = {value}", "ok")
                if errors:
                    self._log(f"SENSÖRLER: PLC okuma hatası: {len(errors)} adet.", "error")

        self._c600_ui(apply)
