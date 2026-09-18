from __future__ import annotations

import socket
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser
import base64
import json
import urllib.parse
import urllib.request

from models import DAMPER_NAMES, FILTER_IDS, SENSOR_NAMES, TestControlState
from build_info import BUILD_VERSION, BUILD_SHA
from updater import check_for_update, start_update


VERSION = BUILD_VERSION
UPDATE_CHECK_INTERVAL_MS = 2 * 60 * 1000
UPDATE_URL = "https://github.com/dincer552/test-kontrol-pa/releases/latest"
C600_API_USERNAME = "ADMIN"
C600_API_PASSWORD = "SBTAdmin!"
C600_API_PIN = "6000"


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
        self._c600_status_var = tk.StringVar(value="Bağlanmadı")
        self._c600_socket: socket.socket | None = None
        self._c600_tx_id = 0
        self._c600_log: tk.Text | None = None
        self._c600_info_vars: dict[str, tk.StringVar] = {}
        self._update_check_running = False
        self._update_available = False
        self._update_button: ttk.Button | None = None
        self._manual_update_button: ttk.Button | None = None
        self._update_build_label: ttk.Label | None = None
        self._init_modern_theme()
        self._build_ui()
        self._update_statuses()
        self.after(2000, self._schedule_update_check)

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
        style.configure("UpdateBuild.TLabel", background=card_bg, foreground="#16a34a", font=("Segoe UI", 8, "bold"))
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

    def _schedule_update_check(self) -> None:
        """Check the published VM manifest every two minutes without blocking Tkinter."""
        self._check_for_update_async()
        self.after(UPDATE_CHECK_INTERVAL_MS, self._schedule_update_check)

    def _check_for_update_async(self, manual: bool = False) -> None:
        if self._update_check_running or getattr(self, "_update_running", False):
            return
        self._update_check_running = True

        def worker() -> None:
            available = False
            update = None
            try:
                update = check_for_update()
                available = bool(update.get("available"))
            except Exception:
                available = False

            def apply() -> None:
                self._update_check_running = False
                self._update_available = available
                button = self._update_button
                if button is not None:
                    button.configure(text="GÜNCELLE", state="normal" if available else "disabled")
                build_label = self._update_build_label
                if build_label is not None:
                    if available and update:
                        build = str(update.get("build") or "").strip()
                        version = str(update.get("version") or "").strip()
                        label = f"Build {build}" if build else (f"v{version.lstrip('vV')}" if version else "Yeni sürüm")
                        build_label.configure(text=label)
                    else:
                        build_label.configure(text="")
                manual_button = self._manual_update_button
                if manual_button is not None:
                    manual_button.configure(state="normal")
                if manual and not available:
                    messagebox.showinfo("GÜNCELLEME", "Programınız güncel.", parent=self)

            self.after(0, apply)

        threading.Thread(target=worker, name="test-kontrol-update-check", daemon=True).start()

    def _manual_update_check(self) -> None:
        """Run an immediate update check requested by the user."""
        button = self._manual_update_button
        if button is None or self._update_check_running or getattr(self, "_update_running", False):
            return
        button.configure(state="disabled")
        self._check_for_update_async(manual=True)

    def _start_update(self) -> None:
        if not self._update_available or self._update_button is None:
            return
        start_update(self, self._update_button)

    def _build_ui(self) -> None:
        # Header mirrors PDF kW Selector: compact white card, blue badge and title.
        header = ttk.Frame(self, style="White.TFrame", padding=(12, 8))
        header.pack(fill="x", pady=(0, 8))
        tk.Label(header, text="TEST", bg="#1a56db", fg="#ffffff", font=("Segoe UI", 10, "bold"), width=5, height=1).pack(side="left", padx=(0, 10))
        title_box = ttk.Frame(header, style="White.TFrame")
        title_box.pack(side="left")
        ttk.Label(title_box, text="TEST KONTROL", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="AHU test, devreye alma, kontrol ve raporlama", style="Muted.TLabel").pack(anchor="w")

        # Manual update check stays available; the install button activates only when a newer build exists.
        update_box = ttk.Frame(header, style="White.TFrame")
        update_box.pack(side="right", padx=(6, 0))
        self._update_button = ttk.Button(update_box, text="GÜNCELLE", style="Secondary.TButton", command=self._start_update, state="disabled")
        self._update_button.pack(side="top")
        self._update_build_label = ttk.Label(update_box, text="", style="UpdateBuild.TLabel")
        self._update_build_label.pack(side="top", pady=(2, 0))
        self._manual_update_button = ttk.Button(
            header,
            text="↻",
            style="Secondary.TButton",
            width=2,
            command=self._manual_update_check,
        )
        self._manual_update_button.pack(side="right", padx=(6, 0))

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
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(3, weight=1)

        ttk.Label(body, text="Climatix C600 / GenericJSON", style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        conn = ttk.LabelFrame(body, text="C600 Bağlantısı", style="Card.TLabelframe", padding=14)
        conn.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(0, 10))
        conn.columnconfigure(1, weight=1)

        ttk.Label(conn, text="Bağlantı:").grid(row=0, column=0, sticky="w", pady=6, padx=(0, 12))
        self._c600_connection_var = tk.StringVar(value="USB / SCOPE TCP Tunnel")
        self._c600_connection_combo = ttk.Combobox(
            conn,
            textvariable=self._c600_connection_var,
            state="readonly",
            values=("USB / SCOPE TCP Tunnel", "Modbus TCP"),
            width=34,
        )
        self._c600_connection_combo.grid(row=0, column=1, sticky="ew", pady=6)
        self._c600_connection_combo.bind("<<ComboboxSelected>>", self._c600_connection_changed)

        ttk.Label(conn, text="Cihaz IP / Host:").grid(row=1, column=0, sticky="w", pady=6, padx=(0, 12))
        self._c600_host_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(conn, textvariable=self._c600_host_var).grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(conn, text="Port:").grid(row=2, column=0, sticky="w", pady=6, padx=(0, 12))
        self._c600_port_var = tk.StringVar(value="4242")
        ttk.Entry(conn, textvariable=self._c600_port_var, width=12).grid(row=2, column=1, sticky="w", pady=6)

        status = tk.Frame(conn, bg="#ecfdf3", highlightbackground="#bbf7d0", highlightthickness=1)
        status.grid(row=0, column=2, rowspan=3, sticky="nsew", padx=(28, 0), pady=2)
        self._c600_dot = tk.Label(status, text="●", bg="#ecfdf3", fg="#16a34a", font=("Segoe UI", 25, "bold"))
        self._c600_dot.grid(row=0, column=0, rowspan=3, padx=(14, 8), pady=10)
        self._c600_status_title = tk.Label(status, text="Bağlanmadı", bg="#ecfdf3", fg="#14532d", font=("Segoe UI", 12, "bold"), anchor="w")
        self._c600_status_title.grid(row=0, column=1, sticky="w", padx=(0, 12), pady=(10, 4))
        self._c600_status_detail = tk.Label(status, text="TCP bağlantısı bekleniyor", bg="#ecfdf3", fg="#166534", font=("Segoe UI", 9), anchor="w", justify="left")
        self._c600_status_detail.grid(row=1, column=1, sticky="w", padx=(0, 12))
        self._c600_status_ping = tk.Label(status, text="Yanıt süresi: —", bg="#ecfdf3", fg="#166534", font=("Segoe UI", 9), anchor="w")
        self._c600_status_ping.grid(row=2, column=1, sticky="w", padx=(0, 12), pady=(2, 10))
        conn.columnconfigure(2, weight=2)

        info = ttk.LabelFrame(body, text="Cihaz Bilgileri", style="Card.TLabelframe", padding=14)
        info.grid(row=1, column=1, rowspan=2, sticky="nsew", padx=(8, 0), pady=(0, 10))
        info.columnconfigure(1, weight=1)
        for r, label, key in ((0, "Model", "model"), (1, "Serial No", "serial"), (2, "Firmware", "firmware"), (3, "Revision", "revision"), (4, "Cihaz Saati", "clock")):
            ttk.Label(info, text=f"{label}:").grid(row=r, column=0, sticky="w", pady=7, padx=(0, 18))
            var = tk.StringVar(value="—")
            self._c600_info_vars[key] = var
            ttk.Label(info, textvariable=var, style="White.TLabel").grid(row=r, column=1, sticky="w", pady=7)

        buttons = ttk.Frame(body, style="White.TFrame")
        buttons.grid(row=2, column=0, sticky="w", pady=(0, 10))
        self._c600_test_btn = ttk.Button(buttons, text="BAĞLANTI TESTİ", style="Primary.TButton", command=self._c600_test)
        self._c600_test_btn.pack(side="left", padx=(0, 8))
        self._c600_disconnect_btn = ttk.Button(buttons, text="AYIR", style="Secondary.TButton", command=self._c600_disconnect)
        self._c600_disconnect_btn.pack(side="left", padx=4)
        self._c600_read_btn = ttk.Button(buttons, text="OKU", style="Secondary.TButton", command=self._c600_read)
        self._c600_read_btn.pack(side="left", padx=4)
        self._c600_write_btn = ttk.Button(buttons, text="YAZ", style="Secondary.TButton", command=self._c600_write)
        self._c600_write_btn.pack(side="left", padx=4)
        self._c600_refresh_btn = ttk.Button(buttons, text="↻ DURUM YENİLE", style="Secondary.TButton", command=self._c600_refresh)
        self._c600_refresh_btn.pack(side="left", padx=4)

        log_frame = ttk.LabelFrame(body, text="İşlem Günlüğü", style="Card.TLabelframe", padding=10)
        log_frame.grid(row=3, column=0, columnspan=2, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)
        ttk.Button(log_frame, text="▣ GÜNLÜĞÜ TEMİZLE", style="Secondary.TButton", command=self._c600_clear_log).grid(row=0, column=0, sticky="e", pady=(0, 6))
        self._c600_log = tk.Text(log_frame, height=10, wrap="word", font=("Segoe UI", 9), bg="#ffffff", fg="#334155", relief="solid", bd=1)
        self._c600_log.grid(row=1, column=0, sticky="nsew")
        self._c600_log.tag_configure("ok", foreground="#16a34a")
        self._c600_log.tag_configure("error", foreground="#b91c1c")
        self._c600_log.tag_configure("muted", foreground="#475569")
        self._c600_log_write("Hazır. C600 bağlantısı bekleniyor.", "muted")

    def _c600_log_write(self, message: str, tag: str = "muted") -> None:
        if self._c600_log is None:
            return
        stamp = time.strftime("%H:%M:%S")
        self._c600_log.insert("end", f"[{stamp}] {message}\n", tag)
        self._c600_log.see("end")

    def _c600_ui(self, callback) -> None:
        try:
            self.after(0, callback)
        except tk.TclError:
            pass

    def _c600_connection_changed(self, _event=None) -> None:
        """Use the correct local port for the selected C600 transport."""
        if self._c600_connection_var.get() == "USB / SCOPE TCP Tunnel":
            self._c600_port_var.set("4242")
        else:
            self._c600_port_var.set("502")

    def _c600_test(self) -> None:
        host = self._c600_host_var.get().strip()
        port_text = self._c600_port_var.get().strip()
        if not host:
            messagebox.showwarning("C600", "Cihaz IP / Host boş bırakılamaz.", parent=self)
            return
        if self._c600_connection_var.get() == "USB / SCOPE TCP Tunnel":
            port_text = "4242"
            self._c600_port_var.set(port_text)
        try:
            port = int(port_text)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showwarning("C600", "Port 1-65535 arasında bir sayı olmalı.", parent=self)
            return
        self._c600_status_var.set(f"Bağlanıyor: {host}:{port}")
        self._c600_status_title.configure(text="Bağlanıyor...")
        self._c600_status_detail.configure(text=f"{host}:{port} adresine bağlanılıyor...")
        self._c600_log_write(f"{self._c600_connection_var.get()} ile {host}:{port} adresine bağlanılıyor...")
        self._c600_test_btn.configure(state="disabled")
        threading.Thread(target=self._c600_connect_worker, args=(host, port), daemon=True).start()

    def _c600_connect_worker(self, host: str, port: int) -> None:
        started = time.perf_counter()
        try:
            sock = socket.create_connection((host, port), timeout=3.0)
            elapsed = (time.perf_counter() - started) * 1000
            old = self._c600_socket
            self._c600_socket = sock
            self.state.c600_connected = True
            if old:
                try: old.close()
                except OSError: pass
            def success() -> None:
                self._c600_status_var.set(f"Bağlandı: {host}:{port}")
                self._c600_status_title.configure(text="Bağlandı - C600")
                self._c600_status_detail.configure(text=f"IP: {host}:{port}\nCihaz: Climatix C600\nDurum: Online")
                self._c600_status_ping.configure(text=f"Yanıt süresi: {elapsed:.0f} ms")
                self._c600_dot.configure(fg="#16a34a")
                self._c600_test_btn.configure(state="normal")
                self._c600_log_write("Bağlantı başarılı.", "ok")
                self._c600_read_device_info()
                self._update_statuses()
            self._c600_ui(success)
        except OSError as exc:
            self.state.c600_connected = False
            def fail() -> None:
                self._c600_status_var.set("Bağlantı başarısız")
                self._c600_status_title.configure(text="Bağlantı başarısız")
                self._c600_status_detail.configure(text=f"{host}:{port}\n{exc}")
                self._c600_status_ping.configure(text="Yanıt süresi: —")
                self._c600_dot.configure(fg="#dc2626")
                self._c600_test_btn.configure(state="normal")
                self._c600_log_write(f"Bağlantı başarısız: {exc}", "error")
                self._update_statuses()
            self._c600_ui(fail)

    def _c600_read_device_info(self) -> None:
        """Read C600 identity values through the Climatix JSON API."""
        threading.Thread(target=self._c600_device_info_worker, daemon=True).start()

    def _c600_json_read(self, point_id: str) -> dict:
        host = self._c600_host_var.get().strip()
        port = int(self._c600_port_var.get().strip())
        if self._c600_connection_var.get() != "USB / SCOPE TCP Tunnel":
            raise OSError("Climatix JSON API yalnızca USB / SCOPE TCP Tunnel bağlantısında kullanılabilir")

        query = urllib.parse.urlencode({
            "fn": "Read",
            "pin": C600_API_PIN,
            "lng": "0",
            "us": "2",
            "id": point_id,
        })
        url = f"http://{host}:{port}/json.html?{query}"
        request = urllib.request.Request(url, method="GET")
        credentials = base64.b64encode(f"{C600_API_USERNAME}:{C600_API_PASSWORD}".encode("ascii")).decode("ascii")
        request.add_header("Authorization", f"Basic {credentials}")
        with urllib.request.urlopen(request, timeout=3.0) as response:
            payload = response.read().decode("utf-8")
        values = json.loads(payload)
        if not isinstance(values, list) or not values or not isinstance(values[0], dict):
            raise ValueError(f"{point_id}: beklenmeyen JSON yanıtı")
        return values[0]

    def _c600_device_info_worker(self) -> None:
        try:
            points = (
                ("34-TARGET", "model", "Model"),
                ("33-TARGET", "serial", "Serial No"),
                ("14-TARGET", "firmware", "Firmware"),
                ("35-TARGET", "revision", "Revision"),
            )
            results: dict[str, dict] = {}
            for point_id, key, _label in points:
                results[key] = self._c600_json_read(point_id)

            clock_points = (
                ("1-SYSTEM CLOCK", "clock_1"),
                ("2-SYSTEM CLOCK", "clock_2"),
                ("3-SYSTEM CLOCK", "clock_3"),
            )
            for point_id, key in clock_points:
                results[key] = self._c600_json_read(point_id)

            model = str(results["model"].get("value", "—")).strip() or "—"
            serial = str(results["serial"].get("value", "—")).strip() or "—"
            firmware = str(results["firmware"].get("value", "—")).strip() or "—"
            revision = str(results["revision"].get("value", "—")).strip() or "—"
            clock_values = [
                str(results[key].get("value", "")).strip()
                for key in ("clock_1", "clock_2", "clock_3")
            ]
            clock_values = [value for value in clock_values if value]
            clock = " / ".join(clock_values) if clock_values else "—"

            def update() -> None:
                self._c600_info_vars["model"].set(model)
                self._c600_info_vars["serial"].set(serial)
                self._c600_info_vars["firmware"].set(firmware)
                self._c600_info_vars["revision"].set(revision)
                self._c600_info_vars["clock"].set(clock)
                self._c600_log_write(f"Model: {model}", "ok")
                self._c600_log_write(f"Serial No: {serial}", "ok")
                self._c600_log_write(f"Firmware: {firmware}", "ok")
                self._c600_log_write(f"Revision: {revision}", "ok")

            self._c600_ui(update)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._c600_ui(lambda: self._c600_log_write(f"Cihaz bilgileri okunamadı: {exc}", "error"))

    def _c600_read(self) -> None:
        if not self.state.c600_connected:
            self._c600_log_write("OKU: Önce C600 bağlantısı kurulmalı.", "error")
            return
        self._c600_log_write("OKU: Cihaz bilgileri okunuyor...")
        self._c600_read_device_info()

    def _c600_write(self) -> None:
        self._c600_log_write("YAZ: Register eşlemesi tanımlanmadığı için güvenli yazma yapılmadı.", "error")

    def _c600_refresh(self) -> None:
        if not self.state.c600_connected:
            self._c600_log_write("DURUM YENİLE: C600 bağlı değil.", "error")
            return
        host = self._c600_host_var.get().strip()
        try:
            port = int(self._c600_port_var.get().strip())
        except ValueError:
            self._c600_log_write("DURUM YENİLE: Geçersiz port.", "error")
            return
        self._c600_log_write("DURUM YENİLE: TCP bağlantısı kontrol ediliyor...")
        threading.Thread(target=self._c600_refresh_worker, args=(host, port), daemon=True).start()

    def _c600_refresh_worker(self, host: str, port: int) -> None:
        started = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=2.0):
                elapsed = (time.perf_counter() - started) * 1000
            self._c600_ui(lambda: self._c600_status_ping.configure(text=f"Yanıt süresi: {elapsed:.0f} ms"))
            self._c600_ui(lambda: self._c600_log_write(f"DURUM YENİLE: Online, {elapsed:.0f} ms.", "ok"))
        except OSError as exc:
            self.state.c600_connected = False
            self._c600_ui(lambda: self._c600_log_write(f"DURUM YENİLE: Bağlantı koptu: {exc}", "error"))
            self._c600_ui(lambda: self._update_statuses())

    def _c600_disconnect(self) -> None:
        sock = self._c600_socket
        self._c600_socket = None
        self.state.c600_connected = False
        if sock:
            try: sock.close()
            except OSError: pass
        self._c600_status_var.set("Bağlanmadı")
        self._c600_status_title.configure(text="Bağlanmadı")
        self._c600_status_detail.configure(text="TCP bağlantısı kapatıldı")
        self._c600_status_ping.configure(text="Yanıt süresi: —")
        self._c600_dot.configure(fg="#94a3b8")
        self._c600_log_write("Bağlantı ayrıldı.", "muted")
        self._update_statuses()

    def _c600_clear_log(self) -> None:
        if self._c600_log is not None:
            self._c600_log.delete("1.0", "end")
        self._c600_log_write("Günlük temizlendi.", "muted")

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

if __name__ == "__main__":
    TestControlApp().mainloop()
