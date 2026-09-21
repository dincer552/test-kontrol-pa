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
        self._damper_widgets: dict[str, tuple[ttk.Label, ttk.Entry]] = {}
        for row, name in enumerate(DAMPER_NAMES):
            label = ttk.Label(card, text=f"{name} Damper Sayısı")
            label.grid(row=row, column=0, sticky="w", pady=7)
            var = tk.StringVar(value=str(self.state.damper_counts[name]))
            self._damper_vars[name] = var
            entry = ttk.Entry(card, textvariable=var, width=20)
            entry.grid(row=row, column=1, sticky="w", pady=7)
            self._damper_widgets[name] = (label, entry)

        # PDF okunana kadar damper türleri görünmez; görünürlük PDF'deki
        # gerçek actuator/damper metinlerine göre belirlenir.
        self._set_damper_visibility({name: False for name in DAMPER_NAMES})

        ttk.Button(
            card,
            text="KAYDET",
            style="Primary.TButton",
            command=lambda: self._save_and_unlock("FİLTRE KONTROL"),
        ).grid(
            row=len(DAMPER_NAMES),
            column=0,
            sticky="w",
            pady=(12, 0),
        )

    def _set_damper_visibility(self, visibility: dict[str, bool]) -> None:
        for name, widgets in self._damper_widgets.items():
            visible = bool(visibility.get(name, False))
            for widget in widgets:
                if visible:
                    widget.grid()
                else:
                    widget.grid_remove()

    def _apply_pdf_damper_visibility(self, damper_types: dict[str, bool]) -> None:
        """PDF keşfine göre damperleri göster; bulunan tipleri varsayılan 1 adet başlat."""
        self._set_damper_visibility(damper_types)
        for name, visible in damper_types.items():
            if visible and self.state.damper_counts.get(name, 0) <= 0:
                self.state.damper_counts[name] = 1
                if name in self._damper_vars:
                    self._damper_vars[name].set("1")

    def _save_damper_state(self) -> None:
        """Damper ekranındaki değerleri ortak state'e aktarır."""
        changed = []
        for name, var in self._damper_vars.items():
            try:
                value = int(var.get() or 0)
            except ValueError:
                value = 0
                var.set("0")
            self.state.damper_counts[name] = max(0, value)
            changed.append(f"{name}={self.state.damper_counts[name]}")
        if changed and hasattr(self, "_log"):
            self._log("DAMPER KONTROL: " + ", ".join(changed), "ok")

    def _clear_damper_ui(self) -> None:
        """Damper ekranını ortak state'teki varsayılan değerlere döndürür."""
        for name, var in self._damper_vars.items():
            var.set(str(self.state.damper_counts[name]))
