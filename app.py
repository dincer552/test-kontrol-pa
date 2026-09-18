from __future__ import annotations

import socket
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from models import DAMPER_NAMES, FILTER_IDS, SENSOR_NAMES, TestControlState


VERSION = "v0.1.0"
UPDATE_URL = "https://github.com/dincer552/test-kontrol-pa/releases/latest"


class TestControlApp(tk.Tk):
    """Standalone Test Control desktop UI, visually aligned with PDF kW Selector."""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"TEST KONTROL {VERSION} — AHU Test ve Devreye Alma")
        self.geometry("1300x820")
        self.minsize(1100, 700)
        self.state = TestControlState()
        self._status_vars: dict[str, tk.StringVar] = {}
        self._status_labels: dict[str, tk.Label] = {}
        self._c600_status_var = tk.StringVar(value="Bağlantı test edilmedi")
        self._init_modern_theme()
        self._build_ui()
        self._update_statuses()

    def _init_modern_theme(self) -> None:
        self.configure(bg="#f0f4f9")
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        bg_canvas = "#f0f4f9"
        card_bg = "#ffffff"
        border = "#e2e8f0"
        primary = "#1a56db"
        text = "#0f172a"
        muted = "#64748b"

        style.configure(".", background=bg_canvas, foreground=text, font=("Segoe UI", 9))
        style.configure("TFrame", background=bg_canvas)
        style.configure("White.TFrame", background=card_bg)
        style.configure("TLabel", background=bg_canvas, foreground=text, font=("Segoe UI", 9))
        style.configure("White.TLabel", background=card_bg, foreground=text, font=("Segoe UI", 9))
        style.configure("Muted.TLabel", background=card_bg, foreground=muted, font=("Segoe UI", 8))
        style.configure("Title.TLabel", background=card_bg, foreground=text, font=("Segoe UI", 13, "bold"))
        style.configure("Badge.TLabel", background="#eff6ff", foreground=primary, font=("Segoe UI", 8, "bold"), padding=(6, 2))
        style.configure("Primary.TButton", background=primary, foreground="#ffffff", font=("Segoe UI", 9, "bold"), borderwidth=0, padding=(12, 6))
        style.map("Primary.TButton", background=[("active", "#1e40af"), ("disabled", "#cbd5e1")])
        style.configure("Secondary.TButton", background="#ffffff", foreground="#334155", font=("Segoe UI", 9), borderwidth=1, bordercolor="#cbd5e1", padding=(8, 4))
        style.map("Secondary.TButton", background=[("active", "#f1f5f9")], bordercolor=[("active", "#94a3b8")])
        style.configure("TNotebook", background=bg_canvas, borderwidth=0)
        style.configure("TNotebook.Tab", background="#e2e8f0", foreground=muted, font=("Segoe UI", 9, "bold"), padding=(14, 7), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", card_bg), ("active", "#e2e8f0")], foreground=[("selected", text), ("active", text)])
        style.configure("TLabelframe", background=card_bg, bordercolor=border, borderwidth=1, relief="solid")
        style.configure("TLabelframe.Label", background=card_bg, foreground=text, font=("Segoe UI", 9, "bold"))
        style.configure("Card.TLabelframe", background=card_bg, bordercolor=border, borderwidth=1, relief="solid")
        style.configure("Card.TLabelframe.Label", background=card_bg, foreground=text, font=("Segoe UI", 9, "bold"))
        style.configure("Treeview", background="#ffffff", foreground=text, fieldbackground="#ffffff", rowheight=26, font=("Segoe UI", 9), borderwidth=1, bordercolor=border)
        style.configure("Treeview.Heading", background="#f8fafc", foreground=text, font=("Segoe UI", 9, "bold"), borderwidth=1, bordercolor=border, padding=6)

    def _open_update_page(self) -> None:
        """Open this project's latest release page."""
        try:
            webbrowser.open(UPDATE_URL, new=2)
        except Exception as exc:
            messagebox.showerror("GÜNCELLE", f"Güncelleme sayfası açılamadı:\n{exc}", parent=self)

    def _build_ui(self) -> None:
        # Header mirrors PDF kW Selector: compact white card, blue badge, title, version.
        header = ttk.Frame(self, style="White.TFrame", padding=(12, 8))
        header.pack(fill="x", pady=(0, 8))
        tk.Label(header, text="TEST", bg="#1a56db", fg="#ffffff", font=("Segoe UI", 10, "bold"), width=5, height=1).pack(side="left", padx=(0, 10))
        title_box = ttk.Frame(header, style="White.TFrame")
        title_box.pack(side="left")
        ttk.Label(title_box, text="TEST KONTROL", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="AHU test, devreye alma, kontrol ve raporlama", style="Muted.TLabel").pack(anchor="w")

        # Update button stays in the upper-right corner, next to the version badge.
        ttk.Button(header, text="GÜNCELLE", style="Secondary.TButton", command=self._open_update_page).pack(side="right", padx=(6, 0))
        ttk.Label(header, text=VERSION, style="Badge.TLabel").pack(side="right", padx=(0, 6))

        # Main notebook uses the same clean white-card visual language.
        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True, padx=10, pady=(0, 0))
        self.tabs = tabs
        self._add_general(tabs)
        self._add_fan(tabs)
        self._add_damper(tabs)
        self._add_filters(tabs)
        self._add_modules(tabs)
        self._add_sensors(tabs)
        self._add_c600(tabs)
        self._add_user_report(tabs)

        self._build_bottom_dock()

    def _tab_frame(self, notebook: ttk.Notebook) -> tuple[ttk.Frame, ttk.Frame]:
        outer = ttk.Frame(notebook, style="White.TFrame")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)
        canvas = tk.Canvas(outer, bg="#ffffff", highlightthickness=0)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas, style="White.TFrame", padding=14)
        body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        window = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"), add="+")
        return outer, body

    def _add_general(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook)
        notebook.add(tab, text="GENEL")
        body.columnconfigure(1, weight=1)

        project = ttk.LabelFrame(body, text="Proje Bilgileri", style="Card.TLabelframe", padding=12)
        project.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        project.columnconfigure(1, weight=1)
        for i, (label, attr) in enumerate((("Order No", "order_no"), ("Proje Adı", "project_name"), ("AHU Adı", "ahu_name"))):
            ttk.Label(project, text=label).grid(row=i, column=0, sticky="w", padx=(0, 12), pady=6)
            var = tk.StringVar(value=getattr(self.state, attr))
            setattr(self, f"_{attr}_var", var)
            ttk.Entry(project, textvariable=var).grid(row=i, column=1, sticky="ew", pady=6)

        checks = ttk.LabelFrame(body, text="Kontrol Durumu", style="Card.TLabelframe", padding=12)
        checks.grid(row=1, column=0, columnspan=2, sticky="ew")
        names = ("Fan Kontrol", "Damper Kontrol", "Filtre Kontrol", "Modüller", "Sensorler", "C600 / GenericJSON", "User", "Rapor")
        for r, name in enumerate(names):
            ttk.Label(checks, text=name).grid(row=r, column=0, sticky="w", pady=4)
            var = tk.StringVar(value="Kontrol Edilmedi")
            self._status_vars[name] = var
            label = tk.Label(checks, textvariable=var, bg="#fef3c7", fg="#92400e", font=("Segoe UI", 9, "bold"), padx=8, pady=3)
            label.grid(row=r, column=1, sticky="w", padx=10, pady=3)
            self._status_labels[name] = label

    def _add_fan(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook)
        notebook.add(tab, text="FAN KONTROL")
        card = ttk.LabelFrame(body, text="Fan Kontrol", style="Card.TLabelframe", padding=12)
        card.pack(fill="x")
        self._fan_var = tk.StringVar(value=self.state.fan_type)
        ttk.Label(card, text="Fan Tipi").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Combobox(card, textvariable=self._fan_var, state="readonly", values=("Danfoss Ziehl-Abegg", "EC Ziehl-Abegg", "EC EBM-Papst"), width=34).grid(row=0, column=1, sticky="w", pady=6)
        for r, label, attr in ((1, "Supply Fan Sayısı", "supply_fan_count"), (2, "Return Fan Sayısı", "return_fan_count"), (3, "Supply Debi", "supply_airflow"), (4, "Return Debi", "return_airflow")):
            ttk.Label(card, text=label).grid(row=r, column=0, sticky="w", pady=6)
            var = tk.StringVar(value=str(getattr(self.state, attr)))
            setattr(self, f"_{attr}_var", var)
            ttk.Entry(card, textvariable=var, width=34).grid(row=r, column=1, sticky="w", pady=6)
        self._airflow_var = tk.BooleanVar(value=self.state.airflow_control_ok)
        self._pressure_var = tk.BooleanVar(value=self.state.pressure_control_ok)
        ttk.Checkbutton(card, text="Debi Kontrol (%25)", variable=self._airflow_var).grid(row=5, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Checkbutton(card, text="Basınç Kontrol", variable=self._pressure_var).grid(row=6, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Button(card, text="KAYDET", style="Primary.TButton", command=self._save).grid(row=7, column=0, sticky="w", pady=(12, 0))

    def _add_damper(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook)
        notebook.add(tab, text="DAMPER KONTROL")
        card = ttk.LabelFrame(body, text="Damper Kontrol", style="Card.TLabelframe", padding=12)
        card.pack(fill="x")
        self._damper_vars: dict[str, tk.StringVar] = {}
        for r, name in enumerate(DAMPER_NAMES):
            ttk.Label(card, text=f"{name} Damper Sayısı").grid(row=r, column=0, sticky="w", pady=7)
            var = tk.StringVar(value=str(self.state.damper_counts[name]))
            self._damper_vars[name] = var
            ttk.Entry(card, textvariable=var, width=20).grid(row=r, column=1, sticky="w", pady=7)
        ttk.Button(card, text="KAYDET", style="Primary.TButton", command=self._save).grid(row=len(DAMPER_NAMES), column=0, sticky="w", pady=(12, 0))

    def _add_filters(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook)
        notebook.add(tab, text="FİLTRE KONTROL")
        card = ttk.LabelFrame(body, text="Filtreler", style="Card.TLabelframe", padding=14)
        card.pack(fill="x")
        self._filter_vars: dict[str, tk.BooleanVar] = {}
        for i, name in enumerate(FILTER_IDS):
            var = tk.BooleanVar(value=self.state.filters[name])
            self._filter_vars[name] = var
            ttk.Checkbutton(card, text=name, variable=var).grid(row=i // 3, column=i % 3, sticky="w", padx=12, pady=6)
        ttk.Button(card, text="KAYDET", style="Primary.TButton", command=self._save).grid(row=6, column=0, sticky="w", pady=(12, 0))

    def _add_modules(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook)
        notebook.add(tab, text="MODÜLLER")
        card = ttk.LabelFrame(body, text="Modül Konfigürasyonu", style="Card.TLabelframe", padding=14)
        card.pack(fill="x")
        self._rotor_var = tk.BooleanVar(value=self.state.rotor_enabled)
        self._run_var = tk.BooleanVar(value=self.state.run_around)
        self._dx_var = tk.BooleanVar(value=self.state.dx_enabled)
        self._hum_var = tk.BooleanVar(value=self.state.humidifier_enabled)
        self._heater_var = tk.BooleanVar(value=self.state.electrical_heater)
        self._co_var = tk.BooleanVar(value=self.state.change_over)
        self._bms_var = tk.BooleanVar(value=self.state.room_bms)
        self._avg_var = tk.BooleanVar(value=self.state.temp_avg_en)
        checks = (("Rotor", self._rotor_var), ("Run Around", self._run_var), ("DX", self._dx_var), ("Nemlendirici", self._hum_var), ("Elektrikli Isıtıcı", self._heater_var), ("ChangeOver", self._co_var), ("Room BMS", self._bms_var), ("Temp Average", self._avg_var))
        for i, (text, var) in enumerate(checks):
            ttk.Checkbutton(card, text=text, variable=var).grid(row=i // 2, column=i % 2, sticky="w", padx=12, pady=7)
        ttk.Label(card, text="DX Kademe (0-5)").grid(row=4, column=0, sticky="w", pady=7)
        self._dx_stage = tk.StringVar(value=str(self.state.dx_stage))
        ttk.Entry(card, textvariable=self._dx_stage, width=12).grid(row=4, column=1, sticky="w")
        ttk.Label(card, text="Nemlendirici Kademe (0-8)").grid(row=5, column=0, sticky="w", pady=7)
        self._hum_stage = tk.StringVar(value=str(self.state.humidifier_stage))
        ttk.Entry(card, textvariable=self._hum_stage, width=12).grid(row=5, column=1, sticky="w")
        ttk.Button(card, text="KAYDET", style="Primary.TButton", command=self._save).grid(row=6, column=0, sticky="w", pady=(12, 0))

    def _add_sensors(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook)
        notebook.add(tab, text="SENSÖRLER")
        card = ttk.LabelFrame(body, text="Sensör Değerleri", style="Card.TLabelframe", padding=14)
        card.pack(fill="x")
        self._sensor_vars: dict[str, tk.StringVar] = {}
        for r, name in enumerate(SENSOR_NAMES):
            ttk.Label(card, text=name).grid(row=r, column=0, sticky="w", pady=6, padx=(0, 20))
            var = tk.StringVar(value=self.state.sensors[name])
            self._sensor_vars[name] = var
            ttk.Entry(card, textvariable=var, width=24).grid(row=r, column=1, sticky="w", pady=6)
        ttk.Button(card, text="KAYDET", style="Primary.TButton", command=self._save).grid(row=len(SENSOR_NAMES), column=0, sticky="w", pady=(12, 0))

    def _add_c600(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook)
        notebook.add(tab, text="C600")
        card = ttk.LabelFrame(body, text="Climatix C600 / GenericJSON", style="Card.TLabelframe", padding=14)
        card.pack(fill="x")
        card.columnconfigure(1, weight=1)

        ttk.Label(card, text="Bağlantı:").grid(row=0, column=0, sticky="w", pady=6, padx=(0, 10))
        ttk.Label(card, text="USB / SCOPE TCP Tunnel").grid(row=0, column=1, sticky="w", pady=6)

        ttk.Label(card, text="Cihaz IP / Host:").grid(row=1, column=0, sticky="w", pady=6, padx=(0, 10))
        self._c600_host_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(card, textvariable=self._c600_host_var, width=28).grid(row=1, column=1, sticky="w", pady=6)

        ttk.Label(card, text="Port:").grid(row=2, column=0, sticky="w", pady=6, padx=(0, 10))
        self._c600_port_var = tk.StringVar(value="4242")
        ttk.Entry(card, textvariable=self._c600_port_var, width=10).grid(row=2, column=1, sticky="w", pady=6)

        ttk.Label(
            card,
            textvariable=self._c600_status_var,
            style="Muted.TLabel",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=6)

        ttk.Button(
            card,
            text="BAĞLANTI TESTİ",
            style="Primary.TButton",
            command=self._c600_test,
        ).grid(row=4, column=0, sticky="w", pady=(12, 0))

    def _add_user_report(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook)
        notebook.add(tab, text="USER / RAPOR")
        card = ttk.LabelFrame(body, text="User / Rapor", style="Card.TLabelframe", padding=14)
        card.pack(fill="x")
        ttk.Label(card, text="Kullanıcı").grid(row=0, column=0, sticky="w", pady=6)
        self._user_var = tk.StringVar(value="")
        ttk.Entry(card, textvariable=self._user_var, width=40).grid(row=0, column=1, sticky="w", pady=6)
        ttk.Button(card, text="KAYDET", style="Primary.TButton", command=self._save).grid(row=1, column=0, sticky="w", pady=(12, 0))

    def _build_bottom_dock(self) -> None:
        dock = ttk.Frame(self, style="White.TFrame", padding=(10, 6))
        dock.pack(side="bottom", fill="x", padx=10, pady=(6, 0))
        ttk.Button(dock, text="✓ KAYDET", style="Primary.TButton", command=self._save).pack(side="left", padx=(0, 6))
        ttk.Button(dock, text="↻ TEMİZLE", style="Secondary.TButton", command=self._clear).pack(side="left", padx=3)
        ttk.Button(dock, text="▣ RAPOR", style="Secondary.TButton", command=self._report).pack(side="left", padx=3)
        ttk.Label(dock, text="DURUM", style="Muted.TLabel").pack(side="right", padx=(20, 4))
        for name in ("FAN", "DAMP", "FİLT", "MOD", "SENS"):
            ttk.Label(dock, text=f"• {name}", style="Badge.TLabel").pack(side="right", padx=2)
        ttk.Label(dock, text="Hazır", style="Muted.TLabel").pack(side="right", padx=(8, 0))

    def _update_statuses(self) -> None:
        mapping = {
            "Fan Kontrol": self.state.fan_control_ok,
            "Damper Kontrol": self.state.damper_control_ok,
            "Filtre Kontrol": self.state.filter_control_ok,
            "Modüller": self.state.modules_ok,
            "Sensorler": self.state.sensors_ok,
            "C600 / GenericJSON": self.state.c600_ok,
            "User": self.state.user_ok,
            "Rapor": self.state.report_ok,
        }
        for name, ok in mapping.items():
            self._status_vars[name].set("Kontrol Edildi" if ok else "Kontrol Edilmedi")
            self._status_labels[name].configure(bg="#dcfce7" if ok else "#fef3c7", fg="#166534" if ok else "#92400e")

    def _save(self) -> None:
        self.state.order_no = self._order_no_var.get()
        self.state.project_name = self._project_name_var.get()
        self.state.ahu_name = self._ahu_name_var.get()
        self.state.fan_type = self._fan_var.get()
        self.state.supply_fan_count = int(self._supply_fan_count_var.get() or 0)
        self.state.return_fan_count = int(self._return_fan_count_var.get() or 0)
        self.state.supply_airflow = self._supply_airflow_var.get()
        self.state.return_airflow = self._return_airflow_var.get()
        self.state.airflow_control_ok = self._airflow_var.get()
        self.state.pressure_control_ok = self._pressure_var.get()
        for name, var in self._damper_vars.items():
            self.state.damper_counts[name] = int(var.get() or 0)
        for name, var in self._filter_vars.items():
            self.state.filters[name] = var.get()
        self.state.rotor_enabled = self._rotor_var.get()
        self.state.run_around = self._run_var.get()
        self.state.dx_enabled = self._dx_var.get()
        self.state.humidifier_enabled = self._hum_var.get()
        self.state.electrical_heater = self._heater_var.get()
        self.state.change_over = self._co_var.get()
        self.state.room_bms = self._bms_var.get()
        self.state.temp_avg_en = self._avg_var.get()
        self.state.dx_stage = int(self._dx_stage.get() or 0)
        self.state.humidifier_stage = int(self._hum_stage.get() or 0)
        for name, var in self._sensor_vars.items():
            self.state.sensors[name] = var.get()
        self.state.user_name = self._user_var.get()
        self.state.recalculate()
        self._update_statuses()

    def _clear(self) -> None:
        self.state = TestControlState()
        for attr in ("order_no", "project_name", "ahu_name"):
            getattr(self, f"_{attr}_var").set("")
        self._fan_var.set(self.state.fan_type)
        self._supply_fan_count_var.set(str(self.state.supply_fan_count))
        self._return_fan_count_var.set(str(self.state.return_fan_count))
        self._supply_airflow_var.set(self.state.supply_airflow)
        self._return_airflow_var.set(self.state.return_airflow)
        self._airflow_var.set(self.state.airflow_control_ok)
        self._pressure_var.set(self.state.pressure_control_ok)
        for name, var in self._damper_vars.items():
            var.set(str(self.state.damper_counts[name]))
        for name, var in self._filter_vars.items():
            var.set(str(self.state.filters[name]))
        self._rotor_var.set(self.state.rotor_enabled)
        self._run_var.set(self.state.run_around)
        self._dx_var.set(self.state.dx_enabled)
        self._hum_var.set(self.state.humidifier_enabled)
        self._heater_var.set(self.state.electrical_heater)
        self._co_var.set(self.state.change_over)
        self._bms_var.set(self.state.room_bms)
        self._avg_var.set(self.state.temp_avg_en)
        self._dx_stage.set(str(self.state.dx_stage))
        self._hum_stage.set(str(self.state.humidifier_stage))
        for name, var in self._sensor_vars.items():
            var.set(self.state.sensors[name])
        self._user_var.set("")
        self._update_statuses()

    def _report(self) -> None:
        messagebox.showinfo("RAPOR", "Rapor oluşturma modülü hazırlanıyor.", parent=self)

    def _c600_test(self) -> None:
        """Test the SCOPE TCP tunnel without blocking the Tkinter UI."""
        host = self._c600_host_var.get().strip()
        port_text = self._c600_port_var.get().strip()

        if not host:
            messagebox.showwarning("C600", "Cihaz IP / Host boş bırakılamaz.", parent=self)
            return

        try:
            port = int(port_text)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showwarning("C600", "Port 1-65535 arasında bir sayı olmalı.", parent=self)
            return

        self._c600_status_var.set(f"Bağlanıyor: {host}:{port} ...")
        self.update_idletasks()

        try:
            with socket.create_connection((host, port), timeout=3.0):
                pass
        except OSError as exc:
            self.state.c600_connected = False
            self._c600_status_var.set(f"Bağlantı başarısız: {host}:{port} — {exc}")
            self._update_statuses()
            messagebox.showerror(
                "C600",
                f"C600 bağlantısı kurulamadı.\\n\\n{host}:{port}\\n{exc}",
                parent=self,
            )
            return

        self.state.c600_connected = True
        self._c600_status_var.set(f"Bağlantı başarılı: {host}:{port}")
        self._update_statuses()
        messagebox.showinfo(
            "C600",
            f"C600 TCP bağlantısı başarılı.\\n\\n{host}:{port}",
            parent=self,
        )


if __name__ == "__main__":
    TestControlApp().mainloop()
