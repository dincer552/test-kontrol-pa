from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from models import SENSOR_NAMES


class SensorTabMixin:
    """SENSÖRLER sekmesinin tüm UI ve state işlemleri."""

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
        for row, name in enumerate(SENSOR_NAMES):
            ttk.Label(
                card,
                text=name,
            ).grid(
                row=row,
                column=0,
                sticky="w",
                pady=6,
                padx=(0, 20),
            )
            var = tk.StringVar(value=self.state.sensors[name])
            self._sensor_vars[name] = var
            ttk.Entry(
                card,
                textvariable=var,
                width=24,
            ).grid(
                row=row,
                column=1,
                sticky="w",
                pady=6,
            )

        ttk.Button(
            card,
            text="KAYDET",
            style="Primary.TButton",
            command=self._save,
        ).grid(
            row=len(SENSOR_NAMES),
            column=0,
            sticky="w",
            pady=(12, 0),
        )

    def _save_sensor_state(self) -> None:
        """Sensör ekranındaki değerleri ortak state'e aktarır."""
        for name, var in self._sensor_vars.items():
            self.state.sensors[name] = var.get()

    def _clear_sensor_ui(self) -> None:
        """Sensör ekranını ortak state'teki varsayılan değerlere döndürür."""
        for name, var in self._sensor_vars.items():
            var.set(self.state.sensors[name])
