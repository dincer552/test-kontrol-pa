from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from models import DAMPER_NAMES


# C600 GenericJSON point names for the damper-count registers.
# The numeric register mapping supplied for this project is kept here as
# metadata so the UI is driven by the controller values rather than PDF data.
DAMPER_REGISTER_POINTS: dict[str, dict[str, object]] = {
    "Fresh": {
        "json_ids": ("FRESHDAMPNUM",),
        "register": "0x2303 0x000024CD",
    },
    "Exhaust": {
        "json_ids": ("EXTDAMPNUM",),
        "register": "0x2303 0x0000742F",
    },
    "Mix": {
        "json_ids": ("MIXDAMPNUM",),
        "register": "0x2303 0x0000970E",
    },
    "Supply": {
        "json_ids": ("SUPPLYDAMPNUM",),
        "register": "0x2303 0x0000A3D8",
    },
    "Return": {
        "json_ids": ("RETURNDAMPNUM",),
        "register": "0x2303 0x000098F9",
    },
    "Bypass": {
        "json_ids": ("BYPASSDAMPNUM",),
        "register": "0x2303 0x00004776",
    },
}


def _parse_damper_count(raw: object) -> int:
    """Convert a GenericJSON numeric value to a non-negative damper count."""
    text = str(raw).strip().replace(",", ".")
    if not text:
        raise ValueError("değer boş")
    value = float(text)
    if not value.is_integer():
        raise ValueError(f"tam sayı olmayan değer: {text}")
    return max(0, int(value))


class DamperTabMixin:
    """DAMPER KONTROL sekmesinin UI ve register tabanlı state işlemleri."""

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
        self._damper_widgets: dict[str, tuple[ttk.Label, ttk.Entry, ttk.Button]] = {}
        for row, name in enumerate(DAMPER_NAMES):
            label = ttk.Label(card, text=f"{name} Damper Sayısı")
            label.grid(row=row, column=0, sticky="w", pady=7)
            var = tk.StringVar(value=str(self.state.damper_counts[name]))
            self._damper_vars[name] = var
            entry = ttk.Entry(card, textvariable=var, width=20, state="readonly")
            entry.grid(row=row, column=1, sticky="w", pady=7)

            manual_button = ttk.Button(
                card,
                text="MANUEL GİRİŞ",
                style="Secondary.TButton",
                command=lambda damper=name: self._enable_manual_damper(damper),
            )
            manual_button.grid(row=row, column=2, sticky="w", padx=(8, 0), pady=7)
            self._damper_widgets[name] = (label, entry, manual_button)

        # Controller values determine visibility during normal operation.
        self._set_damper_visibility({name: False for name in DAMPER_NAMES})

        buttons = ttk.Frame(card, style="White.TFrame")
        buttons.grid(
            row=len(DAMPER_NAMES),
            column=0,
            columnspan=3,
            sticky="w",
            pady=(12, 0),
        )

        self._damper_read_button = ttk.Button(
            buttons,
            text="VERİLERİ ÇEK",
            style="Primary.TButton",
            command=self._fetch_damper_registers,
        )
        self._damper_read_button.pack(side="left", padx=(0, 8))

        self._damper_save_button = ttk.Button(
            buttons,
            text="KAYDET",
            style="Primary.TButton",
            command=lambda: self._save_and_unlock("FİLTRE KONTROL"),
        )
        self._damper_save_button.pack(side="left")

        self._set_damper_entries_state(False)

    def _set_damper_visibility(self, visibility: dict[str, bool]) -> None:
        for name, widgets in self._damper_widgets.items():
            visible = bool(visibility.get(name, False))
            for widget in widgets:
                if visible:
                    widget.grid()
                else:
                    widget.grid_remove()

    def _set_damper_entries_state(self, editable: bool) -> None:
        for _name, (_label, entry, _button) in self._damper_widgets.items():
            if editable:
                entry.configure(state="normal", style="Green.TEntry")
            else:
                entry.configure(state="readonly", style="TEntry")

    def _enable_manual_damper(self, name: str) -> None:
        """Enable manual entry for one damper, matching the fan airflow behavior."""
        widgets = self._damper_widgets.get(name)
        if widgets is None:
            return
        _label, entry, _button = widgets
        entry.configure(state="normal", style="Green.TEntry")
        entry.focus_set()
        entry.selection_range(0, "end")
        self._log(f"DAMPER KONTROL: {name} manuel girişi açıldı.", "muted")

    def _apply_damper_visibility_from_values(self) -> None:
        visibility = {}
        for name, var in self._damper_vars.items():
            try:
                value = max(0, int(var.get() or 0))
            except ValueError:
                value = 0
                var.set("0")
            visibility[name] = value > 0
        self._set_damper_visibility(visibility)

    def _fetch_damper_registers(self) -> None:
        if not self.state.c600_connected:
            self._log("DAMPER: Önce C600 bağlantısı kurulmalı.", "error")
            return

        self._log("DAMPER: Register değerleri okunuyor...", "muted")
        self._damper_read_button.configure(state="disabled")
        threading.Thread(target=self._damper_register_worker, daemon=True).start()

    def _damper_register_worker(self) -> None:
        values: dict[str, int] = {}
        errors: list[str] = []

        for name in DAMPER_NAMES:
            point = DAMPER_REGISTER_POINTS[name]
            try:
                last_error: Exception | None = None
                value: int | None = None
                for json_id in point["json_ids"]:
                    try:
                        result = self._c600_json_read(str(json_id))
                        if not isinstance(result, dict):
                            raise ValueError(f"{json_id}: JSON nesnesi bekleniyor")
                        raw = result.get("value", "")
                        value = _parse_damper_count(raw)
                        break
                    except Exception as exc:
                        last_error = exc
                if value is None:
                    raise last_error or ValueError(f"{name}: register değeri okunamadı")
                values[name] = max(0, value)
            except Exception as exc:
                errors.append(f"{name}: {exc}")

        def apply() -> None:
            self._damper_read_button.configure(state="normal")
            if errors:
                detail = " | ".join(errors)
                self._log("DAMPER: Register okuma hatası: " + detail, "error")
                try:
                    from tkinter import messagebox
                    messagebox.showerror(
                        "DAMPER KONTROL",
                        "Damper registerları okunamadı:\n" + detail,
                        parent=self,
                    )
                except Exception:
                    pass
                return

            for name, value in values.items():
                self.state.damper_counts[name] = value
                self._damper_vars[name].set(str(value))

            self._set_damper_visibility(
                {name: value > 0 for name, value in values.items()}
            )
            self._set_damper_entries_state(False)
            self._log(
                "DAMPER: Register değerleri alındı: "
                + ", ".join(f"{name}={value}" for name, value in values.items()),
                "ok",
            )
            self._update_statuses()

        self._c600_ui(apply)

    def _save_damper_state(self) -> None:
        """Manuel damper değerlerini ortak state'e aktar ve görünürlüğü uygula."""
        changed = []
        for name, var in self._damper_vars.items():
            try:
                value = int(var.get() or 0)
            except ValueError:
                value = 0
                var.set("0")
            value = max(0, value)
            self.state.damper_counts[name] = value
            var.set(str(value))
            changed.append(f"{name}={value}")

        self._set_damper_entries_state(False)
        self._apply_damper_visibility_from_values()

        if changed and hasattr(self, "_log"):
            self._log("DAMPER KONTROL: Manuel değerler kaydedildi: " + ", ".join(changed), "ok")
        self._update_statuses()

    def _clear_damper_ui(self) -> None:
        """Damper ekranını ortak state'teki değerlere döndürür."""
        for name, var in self._damper_vars.items():
            var.set(str(self.state.damper_counts[name]))
        self._set_damper_entries_state(False)
        self._apply_damper_visibility_from_values()
