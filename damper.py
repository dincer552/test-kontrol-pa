from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from models import DAMPER_NAMES


class DamperTabMixin:
    """DAMPER KONTROL sekmesinin tüm UI ve state işlemleri."""

    def _add_damper(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook)
        notebook.add(tab, text="DAMPER KONTROL")

        card = ttk.LabelFrame(
            body,
            text="Damper Kontrol",
            style="Card.TLabelframe",
            padding=12,
        )
        card.pack(fill="x")

        self._damper_vars: dict[str, tk.StringVar] = {}
        for row, name in enumerate(DAMPER_NAMES):
            ttk.Label(card, text=f"{name} Damper Sayısı").grid(
                row=row,
                column=0,
                sticky="w",
                pady=7,
            )
            var = tk.StringVar(value=str(self.state.damper_counts[name]))
            self._damper_vars[name] = var
            ttk.Entry(card, textvariable=var, width=20).grid(
                row=row,
                column=1,
                sticky="w",
                pady=7,
            )

        ttk.Button(
            card,
            text="KAYDET",
            style="Primary.TButton",
            command=self._save,
        ).grid(
            row=len(DAMPER_NAMES),
            column=0,
            sticky="w",
            pady=(12, 0),
        )

    def _save_damper_state(self) -> None:
        """Damper ekranındaki değerleri ortak state'e aktarır."""
        for name, var in self._damper_vars.items():
            try:
                value = int(var.get() or 0)
            except ValueError:
                value = 0
                var.set("0")
            self.state.damper_counts[name] = max(0, value)

    def _clear_damper_ui(self) -> None:
        """Damper ekranını ortak state'teki varsayılan değerlere döndürür."""
        for name, var in self._damper_vars.items():
            var.set(str(self.state.damper_counts[name]))
