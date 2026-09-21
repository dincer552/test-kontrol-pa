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
    "Room CO2 Sensor": ("ROOM_CO2", "ppm"),
    "Room Hum Sensor": ("ROOM_HUM", "%RH"),
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
        self._manual_sensor_rows: dict[str, tuple[ttk.Label, ttk.Entry, ttk.Button]] = {}
        self._manual_sensor_rows_frame: ttk.LabelFrame | None = None

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
        self._sensor_humidity_manual_buttons: dict[str, ttk.Button] = {}
        for name in HUMIDITY_POINTS:
            label = ttk.Label(card, text=f"{name} Nem")
            label.grid(row=row, column=0, sticky="w", pady=6, padx=(0, 20))
            var = tk.StringVar(value="-")
            self._sensor_humidity_vars[name] = var
            entry = ttk.Entry(card, textvariable=var, width=24, state="readonly")
            entry.grid(row=row, column=1, sticky="w", pady=6)
            self._sensor_humidity_widgets[name] = (label, entry)
            button = ttk.Button(
                card,
                text="MANUEL GİRİŞ",
                style="Secondary.TButton",
                command=lambda sensor_name=name: self._toggle_sensor_manual(f"{sensor_name} Humidity"),
            )
            button.grid(row=row, column=2, sticky="w", padx=(8, 0), pady=6)
            self._sensor_humidity_manual_buttons[name] = button
            row += 1

        self._manual_sensor_rows_frame = ttk.Frame(card)
        self._manual_sensor_rows_frame.grid(
            row=row, column=0, columnspan=3, sticky="ew"
        )
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

        manual_card = ttk.LabelFrame(
            card, text="Manuel Sensör Ekle", style="Card.TLabelframe", padding=10
        )
        manual_card.grid(row=row + 2, column=0, columnspan=3, sticky="ew", pady=(14, 0))
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
        self._manual_sensor_rows_frame = manual_card

        self._set_sensor_visibility({name: {"temperature": False, "humidity": False, "co2": False} for name in SENSOR_NAMES})

    def _toggle_sensor_manual(self, name: str) -> None:
        if name in self._sensor_widgets:
            entry = self._sensor_widgets[name][1]
        elif name.endswith(" Humidity") and name[:-9] in self._sensor_humidity_widgets:
            entry = self._sensor_humidity_widgets[name[:-9]][1]
        elif name in self._manual_sensor_rows:
            entry = self._manual_sensor_rows[name][1]
        else:
            return
        entry.configure(state="normal", style="Green.TEntry")
        entry.focus_set()
        entry.selection_range(0, "end")
        if hasattr(self, "_log"):
            self._log(f"SENSÖRLER: {name} manuel değer girişi açıldı.")

    def _add_manual_sensor(self) -> None:
        name = self._manual_sensor_name_var.get().strip()
        value = self._manual_sensor_value_var.get().strip()
        if not name or not value:
            return
        if name in self._sensor_vars or name in self._manual_sensor_rows:
            return

        frame = self._manual_sensor_rows_frame
        if frame is None:
            return
        row = len(self._manual_sensor_rows)
        label = ttk.Label(frame, text=name)
        label.grid(row=row, column=0, sticky="w", pady=6, padx=(0, 20))
        entry = ttk.Entry(frame, width=24, style="Green.TEntry")
        entry.insert(0, value)
        entry.grid(row=row, column=1, sticky="w", pady=6)
        button = ttk.Button(
            frame,
            text="MANUEL GİRİŞ",
            style="Secondary.TButton",
            command=lambda sensor_name=name: self._toggle_sensor_manual(sensor_name),
        )
        button.grid(row=row, column=2, sticky="w", padx=(8, 0), pady=6)
        self._manual_sensor_rows[name] = (label, entry, button)
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
            visible = bool(spec.get("temperature") or spec.get("co2"))
            self._set_widget_visible(widgets, visible)
            button = self._sensor_manual_buttons.get(name)
            if button is not None:
                if visible:
                    button.grid()
                else:
                    button.grid_remove()
        for name, widgets in self._sensor_humidity_widgets.items():
            visible = bool(visibility.get(name, {}).get("humidity"))
            self._set_widget_visible(widgets, visible)
            button = self._sensor_humidity_manual_buttons.get(name)
            if button is not None:
                if visible:
                    button.grid()
                else:
                    button.grid_remove()

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
        for name, (label, entry, button) in self._manual_sensor_rows.items():
            label.destroy()
            entry.destroy()
            button.destroy()
        self._manual_sensor_rows.clear()
        for name, entry_pair in self._sensor_widgets.items():
            entry_pair[1].configure(state="readonly", style="TEntry")
            self._sensor_manual_buttons[name].configure(text="MANUEL GİRİŞ")
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
