from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from models import DAMPER_NAMES, FILTER_IDS, SENSOR_NAMES, TestControlState


class TestControlApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("TEST KONTROL")
        self.geometry("1180x760")
        self.minsize(900, 600)
        self.state = TestControlState()
        self._build_style()
        self._build_header()
        self._build_tabs()

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("StatusOk.TLabel", foreground="#15803d", font=("Segoe UI", 10, "bold"))
        style.configure("StatusTodo.TLabel", foreground="#b45309", font=("Segoe UI", 10, "bold"))

    def _build_header(self) -> None:
        header = ttk.Frame(self, padding=(14, 10))
        header.pack(fill="x")
        ttk.Label(header, text="TEST KONTROL", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="Python / Tkinter", foreground="#64748b").pack(side="left", padx=12)
        ttk.Button(header, text="Kaydet", command=self._save).pack(side="right")

    def _build_tabs(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.notebook = notebook
        self._add_general(notebook)
        self._add_fan(notebook)
        self._add_damper(notebook)
        self._add_filters(notebook)
        self._add_modules(notebook)
        self._add_sensors(notebook)
        self._add_c600(notebook)
        self._add_user_report(notebook)

    def _tab_frame(self, notebook: ttk.Notebook) -> ttk.Frame:
        outer = ttk.Frame(notebook)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)
        canvas = tk.Canvas(outer, highlightthickness=0)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas, padding=14)
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
        return outer, body

    def _add_general(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook)
        notebook.add(tab, text="Genel")
        for i, (label, attr) in enumerate((("Order No", "order_no"), ("Proje Adı", "project_name"), ("AHU Adı", "ahu_name"))):
            ttk.Label(body, text=label).grid(row=i, column=0, sticky="w", pady=6)
            var = tk.StringVar(value=getattr(self.state, attr))
            entry = ttk.Entry(body, textvariable=var, width=55)
            entry.grid(row=i, column=1, sticky="ew", pady=6)
            setattr(self, f"_{attr}_var", var)
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="Kontrol Durumu", style="Section.TLabel").grid(row=4, column=0, columnspan=2, sticky="w", pady=(22, 8))
        for r, name in enumerate(("Fan Kontrol", "Damper Kontrol", "Filtre Kontrol", "Modüller", "Sensorler"), 5):
            ttk.Label(body, text=name).grid(row=r, column=0, sticky="w", pady=4)
            ttk.Label(body, text="Kontrol Edilmedi", style="StatusTodo.TLabel").grid(row=r, column=1, sticky="w", pady=4)

    def _add_fan(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook); notebook.add(tab, text="Fan Kontrol")
        ttk.Label(body, text="Fan Tipi", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self._fan_var = tk.StringVar(value=self.state.fan_type)
        ttk.Combobox(body, textvariable=self._fan_var, state="readonly", values=("Danfoss Ziehl-Abegg", "EC Ziehl-Abegg", "EC EBM-Papst"), width=30).grid(row=0, column=1, sticky="w")
        for r, label, attr in ((1, "Supply Fan Sayısı", "supply_fan_count"), (2, "Return Fan Sayısı", "return_fan_count"), (3, "Supply Debi", "supply_airflow"), (4, "Return Debi", "return_airflow")):
            ttk.Label(body, text=label).grid(row=r, column=0, sticky="w", pady=6)
            var = tk.StringVar(value=str(getattr(self.state, attr))); setattr(self, f"_{attr}_var", var)
            ttk.Entry(body, textvariable=var, width=30).grid(row=r, column=1, sticky="w", pady=6)
        self._airflow_var = tk.BooleanVar(value=self.state.airflow_control_ok); self._pressure_var = tk.BooleanVar(value=self.state.pressure_control_ok)
        ttk.Checkbutton(body, text="Debi Kontrol (%25)", variable=self._airflow_var).grid(row=5, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Checkbutton(body, text="Basınç Kontrol", variable=self._pressure_var).grid(row=6, column=0, columnspan=2, sticky="w", pady=6)

    def _add_damper(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook); notebook.add(tab, text="Damper Kontrol")
        self._damper_vars = {}
        for r, name in enumerate(DAMPER_NAMES):
            ttk.Label(body, text=f"{name} Damper Sayısı").grid(row=r, column=0, sticky="w", pady=7)
            var = tk.StringVar(value=str(self.state.damper_counts[name])); self._damper_vars[name] = var
            ttk.Entry(body, textvariable=var, width=18).grid(row=r, column=1, sticky="w", pady=7)

    def _add_filters(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook); notebook.add(tab, text="Filtre Kontrol")
        self._filter_vars = {}
        for i, name in enumerate(FILTER_IDS):
            var = tk.BooleanVar(value=self.state.filters[name]); self._filter_vars[name] = var
            ttk.Checkbutton(body, text=name, variable=var).grid(row=i // 3, column=i % 3, sticky="w", padx=12, pady=6)

    def _add_modules(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook); notebook.add(tab, text="Modüller")
        self._rotor_var = tk.BooleanVar(value=self.state.rotor_enabled); self._run_var = tk.BooleanVar(value=self.state.run_around)
        self._dx_var = tk.BooleanVar(value=self.state.dx_enabled); self._hum_var = tk.BooleanVar(value=self.state.humidifier_enabled)
        self._heater_var = tk.BooleanVar(value=self.state.electrical_heater); self._co_var = tk.BooleanVar(value=self.state.change_over)
        self._bms_var = tk.BooleanVar(value=self.state.room_bms); self._avg_var = tk.BooleanVar(value=self.state.temp_avg_en)
        checks = (("Rotor", self._rotor_var), ("Run Around", self._run_var), ("DX", self._dx_var), ("Nemlendirici", self._hum_var), ("Elektrikli Isıtıcı", self._heater_var), ("ChangeOver", self._co_var), ("Room BMS", self._bms_var), ("Temp Average", self._avg_var))
        for i, (text, var) in enumerate(checks): ttk.Checkbutton(body, text=text, variable=var).grid(row=i, column=0, sticky="w", pady=6)
        ttk.Label(body, text="DX Kademe (0-5)").grid(row=2, column=1, sticky="w"); self._dx_stage = tk.StringVar(value=str(self.state.dx_stage)); ttk.Entry(body, textvariable=self._dx_stage, width=10).grid(row=2, column=2)
        ttk.Label(body, text="Nemlendirici Kademe (0-8)").grid(row=3, column=1, sticky="w"); self._hum_stage = tk.StringVar(value=str(self.state.humidifier_stage)); ttk.Entry(body, textvariable=self._hum_stage, width=10).grid(row=3, column=2)

    def _add_sensors(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook); notebook.add(tab, text="Sensorler")
        self._sensor_vars = {}
        for r, name in enumerate(SENSOR_NAMES):
            ttk.Label(body, text=name).grid(row=r, column=0, sticky="w", pady=6)
            var = tk.StringVar(value=self.state.sensors[name]); self._sensor_vars[name] = var
            ttk.Entry(body, textvariable=var, width=25).grid(row=r, column=1, sticky="w", pady=6)

    def _add_c600(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook); notebook.add(tab, text="C600")
        ttk.Label(body, text="C600 / GenericJSON", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        for r, label, attr in ((1, "Base URL", "c600_base_url"), (2, "JSON ID", "c600_json_id")):
            ttk.Label(body, text=label).grid(row=r, column=0, sticky="w", pady=6)
            var = tk.StringVar(value=getattr(self.state, attr)); setattr(self, f"_{attr}_var", var); ttk.Entry(body, textvariable=var, width=65).grid(row=r, column=1, sticky="w")
        ttk.Label(body, text="Kimlik bilgileri kaynak koduna gömülmez; bağlantı ayarları daha sonra güvenli yapılandırmadan alınacak.", foreground="#64748b", wraplength=700).grid(row=4, column=0, columnspan=2, sticky="w", pady=18)
        ttk.Button(body, text="Verileri Çek", command=self._read_c600).grid(row=5, column=0, sticky="w")
        self._c600_result = ttk.Label(body, text="Hazır", style="StatusTodo.TLabel"); self._c600_result.grid(row=5, column=1, sticky="w")

    def _add_user_report(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook); notebook.add(tab, text="User / Rapor")
        ttk.Label(body, text="Ad Soyad").grid(row=0, column=0, sticky="w", pady=6)
        self._user_var = tk.StringVar(value=self.state.user_name); ttk.Entry(body, textvariable=self._user_var, width=50).grid(row=0, column=1, sticky="w")
        ttk.Label(body, text="Notlar").grid(row=1, column=0, sticky="nw", pady=6)
        self._notes = tk.Text(body, height=12, width=80); self._notes.grid(row=1, column=1, sticky="nsew", pady=6)
        self._notes.insert("1.0", self.state.notlar)
        body.rowconfigure(1, weight=1); body.columnconfigure(1, weight=1)
        ttk.Label(body, text="Excel/PDF raporu sonraki aşamada eklenecek.", foreground="#64748b").grid(row=2, column=1, sticky="w")

    def _save(self) -> None:
        self.state.set_project_info(self._order_no_var.get(), self._project_name_var.get(), self._ahu_name_var.get())
        self.state.user_name = self._user_var.get().strip(); self.state.notlar = self._notes.get("1.0", "end-1c")
        self.state.fan_type = self._fan_var.get(); self.state.airflow_control_ok = self._airflow_var.get(); self.state.pressure_control_ok = self._pressure_var.get()
        self.state.supply_airflow = self._supply_airflow_var.get(); self.state.return_airflow = self._return_airflow_var.get()
        try: self.state.supply_fan_count = int(self._supply_fan_count_var.get())
        except ValueError: self.state.supply_fan_count = 0
        try: self.state.return_fan_count = int(self._return_fan_count_var.get())
        except ValueError: self.state.return_fan_count = 0
        for name, var in self._damper_vars.items():
            try: self.state.damper_counts[name] = int(var.get())
            except ValueError: self.state.damper_counts[name] = 0
        for name, var in self._filter_vars.items(): self.state.filters[name] = var.get()
        self.state.rotor_enabled = self._rotor_var.get(); self.state.run_around = self._run_var.get(); self.state.dx_enabled = self._dx_var.get(); self.state.humidifier_enabled = self._hum_var.get(); self.state.electrical_heater = self._heater_var.get(); self.state.change_over = self._co_var.get(); self.state.room_bms = self._bms_var.get(); self.state.temp_avg_en = self._avg_var.get()
        try: self.state.dx_stage = max(0, min(5, int(self._dx_stage.get())))
        except ValueError: self.state.dx_stage = 0
        try: self.state.humidifier_stage = max(0, min(8, int(self._hum_stage.get())))
        except ValueError: self.state.humidifier_stage = 0
        for name, var in self._sensor_vars.items(): self.state.sensors[name] = var.get().strip() or "-"
        self.state.c600_base_url = self._c600_base_url_var.get().strip(); self.state.c600_json_id = self._c600_json_id_var.get().strip()
        self._c600_result.configure(text="Durum kaydedildi", style="StatusOk.TLabel")

    def _read_c600(self) -> None:
        self._c600_result.configure(text="C600 bağlantısı sonraki fazda etkinleştirilecek.", style="StatusTodo.TLabel")


if __name__ == "__main__":
    TestControlApp().mainloop()
