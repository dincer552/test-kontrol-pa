from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser
from pathlib import Path

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = None
    TkinterDnD = None

from models import FILTER_IDS, TestControlState
from build_info import BUILD_VERSION, BUILD_SHA
from updater import check_for_update, start_update
from connection import C600ConnectionMixin
from damper import DamperTabMixin
from sensors import SensorTabMixin
from pdf_reader import discover_pdf


VERSION = BUILD_VERSION
UPDATE_CHECK_INTERVAL_MS = 2 * 60 * 1000
UPDATE_URL = "https://github.com/dincer552/test-kontrol-pa/releases/latest"

_TkBase = TkinterDnD.Tk if TkinterDnD is not None else tk.Tk

class TestControlApp(SensorTabMixin, DamperTabMixin, C600ConnectionMixin, _TkBase):
    """Standalone Test Control desktop UI, visually aligned with PDF kW Selector."""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"TEST KONTROL {VERSION} — AHU Test ve Devreye Alma")
        self.geometry("1300x820")
        self.minsize(1100, 700)
        self.state = TestControlState()
        self._status_vars: dict[str, tk.StringVar] = {}
        self._status_labels: dict[str, tk.Label] = {}
        self._init_connection_state()
        self._update_check_running = False
        self._update_available = False
        self._update_button: ttk.Button | None = None
        self._manual_update_button: ttk.Button | None = None
        self._update_build_label: ttk.Label | None = None
        self._init_modern_theme()
        self._build_ui()
        self._configure_tab_flow()
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
                        version = str(update.get("version") or "").strip()
                        display_version = version.lstrip("vV")
                        if display_version.startswith("0.1.0."):
                            display_version = "1.0." + display_version[len("0.1.0."):]
                        label = f"v{display_version}" if display_version else "Yeni sürüm"
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
        update_controls = ttk.Frame(header, style="White.TFrame")
        update_controls.pack(side="right", padx=(6, 0))
        self._manual_update_button = ttk.Button(
            update_controls,
            text="↻",
            style="Secondary.TButton",
            width=2,
            command=self._manual_update_check,
        )
        self._manual_update_button.grid(row=0, column=0, padx=(0, 6), sticky="s")
        self._update_button = ttk.Button(
            update_controls,
            text="GÜNCELLE",
            style="Secondary.TButton",
            command=self._start_update,
            state="disabled",
        )
        self._update_button.grid(row=0, column=1, sticky="s")
        self._update_build_label = ttk.Label(update_controls, text="", style="UpdateBuild.TLabel")
        self._update_build_label.grid(row=1, column=1, pady=(2, 0), sticky="n")

        # Main notebook uses the same clean white-card visual language.
        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True, padx=10, pady=(0, 0))
        self.tabs = tabs
        self._add_c600(tabs)
        self._add_general(tabs)
        self._add_fan(tabs)
        self._add_damper(tabs)
        self._add_filters(tabs)
        self._add_modules(tabs)
        self._add_sensors(tabs)
        self._add_user_report(tabs)

        self._build_bottom_dock()

    def _configure_tab_flow(self) -> None:
        """Create the sequential tab flow; only BAĞLANTI is visible initially."""
        self._tab_ids = {
            self.tabs.tab(i, "text"): self.tabs.tabs()[i]
            for i in range(len(self.tabs.tabs()))
        }
        self._tab_sequence = (
            "BAĞLANTI",
            "PROJE",
            "FAN KONTROL",
            "DAMPER KONTROL",
            "FİLTRE KONTROL",
            "MODÜLLER",
            "SENSÖRLER",
            "USER / RAPOR",
        )
        for tab_name in self._tab_sequence[1:]:
            tab_id = self._tab_ids.get(tab_name)
            if tab_id is not None:
                self.tabs.hide(tab_id)
        self.tabs.select(self._tab_ids["BAĞLANTI"])

    def _set_tab_visible(self, tab_name: str, visible: bool = True) -> None:
        tab_id = getattr(self, "_tab_ids", {}).get(tab_name)
        if tab_id is None:
            return
        try:
            if visible:
                self.tabs.add(tab_id)
            else:
                self.tabs.hide(tab_id)
        except tk.TclError:
            return

    def _on_c600_connection_success(self) -> None:
        """A successful C600 connection unlocks the project tab."""
        self._set_tab_visible("PROJE", True)

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
        notebook.add(tab, text="PROJE")
        body.columnconfigure(0, weight=1)

        project = ttk.LabelFrame(body, text="Proje Bilgileri", style="Card.TLabelframe", padding=12)
        project.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        project.columnconfigure(1, weight=1)
        project.columnconfigure(2, weight=0)

        for i, (label, attr) in enumerate((
            ("Order No", "order_no"),
            ("Proje Adı", "project_name"),
            ("AHU Adı", "ahu_name"),
        )):
            ttk.Label(project, text=label).grid(row=i, column=0, sticky="w", padx=(0, 12), pady=6)
            var = tk.StringVar(value=getattr(self.state, attr))
            setattr(self, f"_{attr}_var", var)
            ttk.Label(project, textvariable=var, style="White.TLabel").grid(
                row=i, column=1, sticky="w", pady=6
            )

        # PDF kW Selector'daki PDF alma kutusunun ayni tasarim/drag davranisi.
        pdf_box = ttk.Frame(project, style="White.TFrame", padding=(12, 0, 0, 0))
        pdf_box.grid(row=0, column=2, rowspan=3, sticky="ne")

        inner_box = tk.Frame(
            pdf_box, bg="#ffffff", highlightbackground="#e2e8f0",
            highlightthickness=1, padx=8, pady=8, width=360, height=150
        )
        inner_box.pack(fill="both", expand=True)
        inner_box.pack_propagate(False)

        head_row = tk.Frame(inner_box, bg="#ffffff")
        head_row.pack(fill="x", pady=(0, 6))
        tk.Label(
            head_row, text=" PDF ", bg="#eff6ff", fg="#2563eb",
            font=("Segoe UI", 9, "bold"), relief="flat"
        ).pack(side="left", padx=(0, 6))

        info_col = tk.Frame(head_row, bg="#ffffff")
        info_col.pack(side="left")
        tk.Label(
            info_col, text="AHU PROJE PDF", bg="#ffffff", fg="#0f172a",
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")
        tk.Label(
            info_col, text="Proje bilgileri PDF'den otomatik alınır",
            bg="#ffffff", fg="#94a3b8", font=("Segoe UI", 8)
        ).pack(anchor="w")

        btn_col = tk.Frame(head_row, bg="#ffffff")
        btn_col.pack(side="right")
        self._pdf_count_label = tk.Label(
            btn_col, text="0 PDF", bg="#ffffff", fg="#475569",
            font=("Segoe UI", 8, "bold"), relief="solid", bd=1,
            padx=6, pady=2
        )
        self._pdf_count_label.pack(side="left", padx=(0, 6))
        ttk.Button(
            btn_col, text="+ PDF EKLE", style="Secondary.TButton",
            command=self._select_pdf
        ).pack(side="left", padx=2)

        drop_banner = tk.Frame(
            inner_box, bg="#eff6ff", highlightbackground="#2563eb",
            highlightthickness=2, padx=8, pady=6
        )
        self._pdf_banner_label = tk.Label(
            drop_banner, text="⬇  PDF BURAYA BIRAKIN  ⬇",
            bg="#eff6ff", fg="#1d4ed8", font=("Segoe UI", 9, "bold")
        )
        self._pdf_banner_label.pack(fill="both", expand=True)

        list_container = tk.Frame(
            inner_box, bg="#f8fafc",
            highlightbackground="#e2e8f0", highlightthickness=1
        )
        list_container.pack(fill="both", expand=True, pady=(4, 0))
        self._pdf_list_label = tk.Label(
            list_container, text="PDF bekleniyor...", bg="#f8fafc",
            fg="#94a3b8", font=("Segoe UI", 8), anchor="w"
        )
        self._pdf_list_label.pack(fill="both", expand=True, padx=8)

        self._pdf_inner_box = inner_box
        self._pdf_head_row = head_row
        self._pdf_drop_banner = drop_banner
        self._pdf_list_container = list_container
        self._pdf_is_drag_active = False
        self._pdf_anim_job = None

        if DND_FILES is not None:
            inner_box.drop_target_register(DND_FILES)
            inner_box.dnd_bind("<<DropEnter>>", self._pdf_drag_enter)
            inner_box.dnd_bind("<<DropPosition>>", self._pdf_drag_position)
            inner_box.dnd_bind("<<DropLeave>>", self._pdf_drag_leave)
            inner_box.dnd_bind("<<Drop>>", self._drop_pdf)

        self._pdf_status_var = tk.StringVar(value="")
        ttk.Label(project, textvariable=self._pdf_status_var, style="Muted.TLabel").grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(4, 0)
        )

        checks = ttk.LabelFrame(body, text="Kontrol Durumu", style="Card.TLabelframe", padding=12)
        checks.grid(row=1, column=0, sticky="ew")
        names = ("Fan Kontrol", "Damper Kontrol", "Filtre Kontrol", "Modüller", "Sensorler", "C600 / GenericJSON", "User", "Rapor")
        for r, name in enumerate(names):
            ttk.Label(checks, text=name).grid(row=r, column=0, sticky="w", pady=4)
            var = tk.StringVar(value="Kontrol Edilmedi")
            self._status_vars[name] = var
            label = tk.Label(checks, textvariable=var, bg="#fef3c7", fg="#92400e", font=("Segoe UI", 9, "bold"), padx=8, pady=3)
            label.grid(row=r, column=1, sticky="w", padx=10, pady=3)
            self._status_labels[name] = label

    def _pdf_drag_enter(self, event):
        self._set_pdf_drag_active(True)
        return getattr(event, "action", "copy")

    def _pdf_drag_position(self, event):
        self._set_pdf_drag_active(True)
        return getattr(event, "action", "copy")

    def _pdf_drag_leave(self, event):
        self._set_pdf_drag_active(False)
        return getattr(event, "action", "copy")

    def _set_pdf_drag_active(self, active: bool) -> None:
        if getattr(self, "_pdf_is_drag_active", False) == active:
            return
        self._pdf_is_drag_active = active
        job = getattr(self, "_pdf_anim_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
            self._pdf_anim_job = None
        if active:
            self._pdf_drop_banner.pack(
                fill="x", pady=(0, 6), before=self._pdf_list_container
            )
            self._run_pdf_drag_pulse(0)
        else:
            self._pdf_drop_banner.pack_forget()
            self._pdf_inner_box.configure(
                highlightbackground="#e2e8f0", highlightthickness=1, bg="#ffffff"
            )
            self._pdf_head_row.configure(bg="#ffffff")
            self._pdf_banner_label.configure(
                bg="#eff6ff", fg="#1d4ed8",
                text="⬇  PDF BURAYA BIRAKIN  ⬇"
            )

    def _run_pdf_drag_pulse(self, step: int) -> None:
        if not getattr(self, "_pdf_is_drag_active", False):
            return
        palette = ("#2563eb", "#3b82f6", "#60a5fa", "#3b82f6")
        icons = ("⬇  PDF BURAYA BIRAKIN  ⬇", "⤓  PDF BURAYA BIRAKIN  ⤓")
        color = palette[step % len(palette)]
        try:
            self._pdf_inner_box.configure(
                highlightbackground=color, highlightthickness=2, bg="#eff6ff"
            )
            self._pdf_head_row.configure(bg="#eff6ff")
            self._pdf_drop_banner.configure(
                highlightbackground=color, bg="#eff6ff"
            )
            self._pdf_banner_label.configure(
                bg="#eff6ff", fg="#1d4ed8",
                text=icons[(step // 2) % len(icons)]
            )
        except Exception:
            return
        self._pdf_anim_job = self.after(
            130, lambda: self._run_pdf_drag_pulse(step + 1)
        )

    def _select_pdf(self) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="AHU PDF seç",
            filetypes=[("PDF dosyaları", "*.pdf"), ("Tüm dosyalar", "*.*")]
        )
        if path:
            self._load_pdf(path)

    def _drop_pdf(self, event) -> None:
        self._set_pdf_drag_active(False)
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            paths = (event.data,)
        pdfs = [
            Path(p).expanduser() for p in paths
            if str(p).lower().endswith(".pdf")
        ]
        if pdfs:
            self._load_pdf(str(pdfs[0]))

    def _load_pdf(self, path: str) -> None:
        pdf_path = Path(path)
        if not pdf_path.is_file():
            self._pdf_status_var.set("PDF dosyası bulunamadı.")
            return
        try:
            result = discover_pdf(pdf_path)
        except Exception as exc:
            self._pdf_status_var.set("")
            return

        self._pdf_count_label.configure(text="1 PDF")
        self._pdf_list_label.configure(
            text=f"✓  {pdf_path.name}",
            fg="#166534", font=("Segoe UI", 9, "bold")
        )
        self._pdf_status_var.set(f"Okundu: {pdf_path.stem}")
        self._apply_pdf_damper_visibility(result.damper_types)
        self._apply_pdf_sensor_visibility(result.sensor_types)
        # PDF is the approval/input point for opening the next sequential tab.
        self._set_tab_visible("FAN KONTROL", True)
        if result.order_no:
            self._order_no_var.set(result.order_no)
            self.state.order_no = result.order_no
        if result.project_name:
            self._project_name_var.set(result.project_name)
            self.state.project_name = result.project_name
        if result.ahu_name:
            self._ahu_name_var.set(result.ahu_name)
            self.state.ahu_name = result.ahu_name

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
        ttk.Button(card, text="KAYDET", style="Primary.TButton", command=self._save).grid(row=2, column=0, sticky="w", pady=(12, 0))

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
        self._save_damper_state()
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
        self._save_sensor_state()
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
        self._clear_damper_ui()
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
        self._clear_sensor_ui()
        self._user_var.set("")
        self._update_statuses()

    def _report(self) -> None:
        messagebox.showinfo("RAPOR", "Rapor oluşturma modülü hazırlanıyor.", parent=self)

if __name__ == "__main__":
    TestControlApp().mainloop()
