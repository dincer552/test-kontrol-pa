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
from report import save_report_dialog


FAN_TYPE_REGISTERS = {
    "Aspiratör": (
        ("Danfoss", "EXHDANFOSSINVNU"),
        ("EBM-Papst", "EXHEBMFANNUM"),
        ("Ziehl-Abegg", "EXZIEHLABEGGFAN"),
        ("Honeywell", "EXHHONEYWELLINV"),
    ),
    "Vantilatör": (
        ("Danfoss", "DANFOSSINVNUM"),
        ("EBM-Papst", "EBMFANNUM"),
        ("Ziehl-Abegg", "ZIEHLABEGGFANNU"),
        ("Honeywell", "HONEYWELLINVNUM"),
    ),
}

MODULE_REGISTER_POINTS = {
    "electrical_heater": "ELECHEATERENB",
    "pre_electrical_heater": "PREELECHEATEREN",
    "run_around": "RUNAROUNDENB",
    "dx_capacity": "DXCAPACITY",
    "change_over": "COVERCONTSELECT",
    "humidifier_capacity": "HUMIFIERCAPACIT",
    "rotor_mode": "ROTORCONTSELECT",
}


VERSION = BUILD_VERSION
UPDATE_CHECK_INTERVAL_MS = 2 * 60 * 1000
UPDATE_URL = "https://github.com/dincer552/test-kontrol-pa/releases/latest"

_TkBase = TkinterDnD.Tk if TkinterDnD is not None else tk.Tk

class TestControlApp(SensorTabMixin, DamperTabMixin, C600ConnectionMixin, _TkBase):
    """Standalone Test Control desktop UI, visually aligned with PDF kW Selector."""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"Test Kontrol {VERSION} — AHU Test ve Devreye Alma")
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
        style.configure("Green.TEntry", fieldbackground="#dcfce7", foreground="#166534")
        style.configure("Green.TCheckbutton", background=card_bg, foreground="#166534")

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
                    button.configure(text="Güncelle", state="normal" if available else "disabled")
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
        tk.Label(header, text="Test", bg="#1a56db", fg="#ffffff", font=("Segoe UI", 10, "bold"), width=5, height=1).pack(side="left", padx=(0, 10))
        title_box = ttk.Frame(header, style="White.TFrame")
        title_box.pack(side="left")
        ttk.Label(title_box, text="Test Kontrol", style="Title.TLabel").pack(anchor="w")
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
            text="Güncelle",
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
        """Unlock workflow tabs in order; BAĞLANTI is the only initial tab."""
        tab_ids = self.tabs.tabs()
        self._tab_ids = {
            self.tabs.tab(i, "text"): tab_ids[i]
            for i in range(len(tab_ids))
        }
        self._tab_sequence = (
            "Bağlantı",
            "Proje",
            "Fan Kontrol",
            "Damper Kontrol",
            "Filtre Kontrol",
            "Modüller",
            "Sensörler",
            "Rapor",
        )
        self._tab_positions = {
            name: index for index, name in enumerate(self._tab_sequence)
        }
        # Use the notebook tab state consistently. `hide()` removes a tab from
        # the visible tab bar but is not restored by `tab(..., state="normal")`.
        # The workflow unlocker below restores tabs via the state API, so the
        # initial lock must use the same mechanism.
        for tab_name in self._tab_sequence[1:]:
            tab_id = self._tab_ids.get(tab_name)
            if tab_id is not None:
                self.tabs.tab(tab_id, state="hidden")
        self.tabs.select(self._tab_ids["Bağlantı"])

    def _set_tab_visible(self, tab_name: str, visible: bool = True) -> None:
        """Show/hide an already-created ttk.Notebook tab without changing its order."""
        tab_id = getattr(self, "_tab_ids", {}).get(tab_name)
        if tab_id is None:
            return
        try:
            if visible:
                # The tab remains in Notebook.tabs() even while hidden.
                # Re-adding/inserting it is therefore unnecessary and can
                # leave the tab hidden. Explicitly restore its state instead.
                self.tabs.tab(tab_id, state="normal")
            else:
                self.tabs.tab(tab_id, state="hidden")
        except tk.TclError:
            return

    def _on_c600_connection_success(self) -> None:
        """A successful C600 connection unlocks the project tab."""
        self._set_tab_visible("Proje", True)

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
        notebook.add(tab, text="Proje")
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
            info_col, text="AHU Proje PDF", bg="#ffffff", fg="#0f172a",
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
            btn_col, text="+ PDF Ekle", style="Secondary.TButton",
            command=self._select_pdf
        ).pack(side="left", padx=2)

        drop_banner = tk.Frame(
            inner_box, bg="#eff6ff", highlightbackground="#2563eb",
            highlightthickness=2, padx=8, pady=6
        )
        self._pdf_banner_label = tk.Label(
            drop_banner, text="⬇  PDF Buraya Bırakın  ⬇",
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
            self._log(f"PROJE: PDF bulunamadı: {path}", "error")
            return
        self._log(f"PROJE: PDF okunuyor: {pdf_path.name}")
        try:
            result = discover_pdf(pdf_path)
        except Exception as exc:
            self._pdf_status_var.set("")
            self._log(f"PROJE: PDF okuma hatası: {exc}", "error")
            return

        self._pdf_count_label.configure(text="1 PDF")
        self._pdf_list_label.configure(
            text=f"✓  {pdf_path.name}",
            fg="#166534", font=("Segoe UI", 9, "bold")
        )
        self._pdf_status_var.set(f"Okundu: {pdf_path.stem}")
        self._log(f"PROJE: PDF okundu: {pdf_path.name}", "ok")
        self._log(
            f"PROJE: keşif tamamlandı — damper={sum(result.damper_types.values())}, sensör={len(result.sensor_types)}"
        )
        self._confirm_sensor_matches(result.sensor_match_candidates)
        # Damper visibility is now driven by controller registers, not PDF discovery.
        self._apply_pdf_sensor_visibility(result.sensor_types)
        # PDF is the approval/input point for opening the next sequential tab.
        self._set_tab_visible("Fan Kontrol", True)
        if result.order_no:
            self._order_no_var.set(result.order_no)
            self.state.order_no = result.order_no
        if result.project_name:
            self._project_name_var.set(result.project_name)
            self.state.project_name = result.project_name
        if result.ahu_name:
            self._ahu_name_var.set(result.ahu_name)
            self.state.ahu_name = result.ahu_name

    def _confirm_sensor_matches(self, candidates: dict[str, str]) -> None:
        if not candidates:
            return
        self._sensor_pdf_matches = {}
        for sensor_name, pdf_label in candidates.items():
            accepted = messagebox.askyesno(
                "SENSÖR EŞLEŞTİRME",
                f"PDF'de benzer bir sensör adı bulundu:\n\n"
                f"PDF: {pdf_label}\n\n"
                f"'{sensor_name}' olarak eşleştirilsin mi?",
                parent=self,
            )
            if accepted:
                self._sensor_pdf_matches[sensor_name] = pdf_label
                self._log(
                    f"PROJE: sensör eşleştirildi — {pdf_label} → {sensor_name}",
                    "ok",
                )
            else:
                self._log(
                    f"PROJE: sensör eşleştirmesi reddedildi — {pdf_label} ≠ {sensor_name}"
                )

    def _add_fan(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook)
        notebook.add(tab, text="Fan Kontrol")
        card = ttk.LabelFrame(body, text="Fan Kontrol", style="Card.TLabelframe", padding=12)
        card.pack(fill="x")

        self._aspirator_fan_type_var = tk.StringVar(value="")
        self._aspirator_fan_count_var = tk.StringVar(value="0")
        self._ventilator_fan_type_var = tk.StringVar(value="")
        self._ventilator_fan_count_var = tk.StringVar(value="0")

        for row, label, type_var, count_var in (
            (0, "Aspiratör Fan Tipi", self._aspirator_fan_type_var, self._aspirator_fan_count_var),
            (1, "Aspiratör Fan Sayısı", None, self._aspirator_fan_count_var),
            (2, "Vantilatör Fan Tipi", self._ventilator_fan_type_var, self._ventilator_fan_count_var),
            (3, "Vantilatör Fan Sayısı", None, self._ventilator_fan_count_var),
        ):
            ttk.Label(card, text=label).grid(row=row, column=0, sticky="w", pady=6)
            var = type_var if type_var is not None else count_var
            ttk.Entry(card, textvariable=var, width=34, state="readonly").grid(
                row=row, column=1, sticky="w", pady=6
            )

        ttk.Label(card, text="Supply Debi (%25)").grid(row=4, column=0, sticky="w", pady=6)
        self._supply_airflow_var = tk.StringVar(value=self.state.supply_airflow)
        self._supply_airflow_entry = ttk.Entry(
            card, textvariable=self._supply_airflow_var, width=34, state="readonly"
        )
        self._supply_airflow_entry.grid(row=4, column=1, sticky="w", pady=6)
        ttk.Button(
            card, text="Manuel Giriş", style="Secondary.TButton",
            command=lambda: self._enable_manual_airflow("supply")
        ).grid(row=4, column=2, sticky="w", padx=(8, 0), pady=6)

        ttk.Label(card, text="Return Debi (%25)").grid(row=5, column=0, sticky="w", pady=6)
        self._return_airflow_var = tk.StringVar(value=self.state.return_airflow)
        self._return_airflow_entry = ttk.Entry(
            card, textvariable=self._return_airflow_var, width=34, state="readonly"
        )
        self._return_airflow_entry.grid(row=5, column=1, sticky="w", pady=6)
        ttk.Button(
            card, text="Manuel Giriş", style="Secondary.TButton",
            command=lambda: self._enable_manual_airflow("return")
        ).grid(row=5, column=2, sticky="w", padx=(8, 0), pady=6)

        buttons = ttk.Frame(card, style="White.TFrame")
        buttons.grid(row=6, column=0, columnspan=3, sticky="w", pady=(12, 0))
        self._fan_read_button = ttk.Button(
            buttons, text="Verileri Çek", style="Secondary.TButton",
            command=self._read_fan_airflows
        )
        self._fan_read_button.pack(side="left", padx=(0, 8))
        ttk.Button(
            buttons, text="Kaydet", style="Primary.TButton",
            command=self._save_fan_and_unlock_damper
        ).pack(side="left")

    def _enable_manual_airflow(self, side: str) -> None:
        """Allow a PLC airflow field to be edited manually when requested."""
        entry = self._supply_airflow_entry if side == "supply" else self._return_airflow_entry
        entry.configure(state="normal", style="Green.TEntry")
        entry.focus_set()
        entry.selection_range(0, "end")

    def _read_fan_airflows(self) -> None:
        """Read Supply/Return airflow values from the C600 GenericJSON points."""
        if not self.state.c600_connected:
            messagebox.showwarning("FAN KONTROL", "Önce C600 bağlantısı kurulmalı.", parent=self)
            self._log("FAN KONTROL: Veri çekme isteği reddedildi; C600 bağlı değil.", "error")
            return
        self._log("FAN KONTROL: Fan bilgileri ve Supply/Return debi okunuyor...")
        self._fan_read_button.configure(state="disabled")
        threading.Thread(target=self._fan_data_worker, daemon=True).start()

    def _fan_data_worker(self) -> None:
        results: dict[str, str] = {}
        error: Exception | None = None
        conflicts: list[str] = []
        try:
            for group, registers in FAN_TYPE_REGISTERS.items():
                active: list[tuple[str, str, int]] = []
                for fan_type, point_id in registers:
                    result = self._c600_json_read(point_id)
                    raw = str(result.get("value", "")).strip()
                    if not raw:
                        raw = "0"
                    value = int(float(raw.replace(",", ".")))
                    if value > 0:
                        active.append((fan_type, point_id, value))

                if len(active) > 1:
                    conflicts.append(
                        f"{group}: " + ", ".join(f"{fan_type}={value}" for fan_type, _point, value in active)
                    )
                if active:
                    fan_type, point_id, value = active[0]
                    results[f"{group}_type"] = fan_type
                    results[f"{group}_count"] = str(value)
                else:
                    results[f"{group}_type"] = "Yok"
                    results[f"{group}_count"] = "0"

            for point_id in ("AIR_FLOW", "1-AIR_FLOW"):
                result = self._c600_json_read(point_id)
                value = str(result.get("value", "")).strip()
                if not value:
                    raise ValueError(f"{point_id}: değer boş")
                results[point_id] = value
        except Exception as exc:
            error = exc

        def apply() -> None:
            self._fan_read_button.configure(state="normal")
            if error is not None:
                self._log(f"FAN KONTROL: Debi okuma hatası: {error}", "error")
                messagebox.showerror("FAN KONTROL", f"Debi verileri okunamadı:\n{error}", parent=self)
                return
            self._aspirator_fan_type_var.set(results["Aspiratör_type"])
            self._aspirator_fan_count_var.set(results["Aspiratör_count"])
            self._ventilator_fan_type_var.set(results["Vantilatör_type"])
            self._ventilator_fan_count_var.set(results["Vantilatör_count"])
            self._supply_airflow_var.set(results["AIR_FLOW"])
            self._return_airflow_var.set(results["1-AIR_FLOW"])
            self.state.fan_type = (
                f"Aspiratör: {results['Aspiratör_type']} | "
                f"Vantilatör: {results['Vantilatör_type']}"
            )
            self.state.supply_fan_count = int(results["Vantilatör_count"])
            self.state.return_fan_count = int(results["Aspiratör_count"])
            self.state.supply_airflow = results["AIR_FLOW"]
            self.state.return_airflow = results["1-AIR_FLOW"]
            self._log(f"FAN KONTROL: Aspiratör={results['Aspiratör_type']} / {results['Aspiratör_count']}", "ok")
            self._log(f"FAN KONTROL: Vantilatör={results['Vantilatör_type']} / {results['Vantilatör_count']}", "ok")
            self._log(f"FAN KONTROL: AIR_FLOW={results['AIR_FLOW']}", "ok")
            self._log(f"FAN KONTROL: 1-AIR_FLOW={results['1-AIR_FLOW']}", "ok")
            if conflicts:
                self._log("FAN KONTROL: Birden fazla aktif fan tipi: " + " | ".join(conflicts), "error")
            self._update_statuses()

        self._c600_ui(apply)

    def _add_filters(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook)
        notebook.add(tab, text="Filtre Kontrol")
        card = ttk.LabelFrame(body, text="Filtreler", style="Card.TLabelframe", padding=14)
        card.pack(fill="x")
        self._filter_vars: dict[str, tk.BooleanVar] = {}
        for i, name in enumerate(FILTER_IDS):
            var = tk.BooleanVar(value=self.state.filters[name])
            self._filter_vars[name] = var
            ttk.Checkbutton(card, text=name, variable=var).grid(row=i // 3, column=i % 3, sticky="w", padx=12, pady=6)
        ttk.Button(card, text="Kaydet", style="Primary.TButton", command=lambda: self._save_and_unlock("Modüller")).grid(row=2, column=0, sticky="w", pady=(12, 0))

    def _add_modules(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook)
        notebook.add(tab, text="Modüller")
        card = ttk.LabelFrame(body, text="Modül Konfigürasyonu", style="Card.TLabelframe", padding=14)
        card.pack(fill="x")
        card.columnconfigure(1, weight=1)

        self._module_vars = {}
        self._module_rows = {}
        module_specs = (
            ("Rotor", "rotor", 0),
            ("Around", "run_around", 1),
            ("DX", "dx", 2),
            ("ChangeOverValve", "change_over", 3),
            ("Nemlendirici", "humidifier", 4),
        )
        for label, key, row in module_specs:
            var = tk.StringVar(value="—")
            self._module_vars[key] = var
            label_widget = ttk.Label(card, text=label)
            # Replace the temporary label with a stored widget so the whole row
            # can be hidden without hiding the complete module card.
            label_widget.grid(row=row, column=0, sticky="w", padx=12, pady=7)
            entry = ttk.Entry(card, textvariable=var, width=28, state="readonly")
            entry.grid(row=row, column=1, sticky="w", pady=7)
            self._module_rows[key] = (label_widget, entry)

        self._heater_stage_vars = {
            "electrical": tk.StringVar(value=str(max(1, min(3, self.state.electrical_stage_count)))),
            "pre_electrical": tk.StringVar(value=str(max(1, min(3, self.state.pre_electrical_stage_count)))),
        }
        self._heater_table_frames = {}
        self._heater_table_values = {"electrical": {}, "pre_electrical": {}}

        self._create_heater_table(card, "electrical", "Elektrikli Isıtıcı R/S/T Akım", row=5)
        self._create_heater_table(card, "pre_electrical", "Pre Elektrikli Isıtıcı R/S/T Akım", row=6)

        buttons = ttk.Frame(card, style="White.TFrame")
        buttons.grid(row=7, column=0, columnspan=3, sticky="w", pady=(12, 0))
        self._module_read_button = ttk.Button(
            buttons, text="Verileri Çek", style="Secondary.TButton", command=self._read_module_data
        )
        self._module_read_button.pack(side="left", padx=(0, 8))
        ttk.Button(
            buttons, text="Kaydet", style="Primary.TButton",
            command=lambda: self._save_and_unlock("Sensörler")
        ).pack(side="left")

        self._set_module_visibility({
            "electrical_heater": self.state.electrical_heater,
            "pre_electrical_heater": self.state.pre_electrical_heater,
            "run_around": self.state.run_around,
            "dx": self.state.dx_enabled,
            "change_over": self.state.change_over,
            "humidifier": self.state.humidifier_enabled,
            "rotor": self.state.rotor_enabled,
        })

    def _create_heater_table(self, parent: ttk.Frame, kind: str, title: str, row: int) -> None:
        frame = ttk.LabelFrame(parent, text=title, style="Card.TLabelframe", padding=10)
        frame.grid(row=row, column=0, columnspan=3, sticky="w", padx=12, pady=(6, 2))
        self._heater_table_frames[kind] = frame

        header = ttk.Frame(frame, style="White.TFrame")
        header.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        ttk.Label(header, text="Kademe Sayısı").pack(side="left", padx=(0, 8))
        spin = ttk.Spinbox(
            header, from_=1, to=3, width=5, textvariable=self._heater_stage_vars[kind],
            command=lambda k=kind: self._rebuild_heater_table(k)
        )
        spin.pack(side="left")
        spin.bind("<FocusOut>", lambda _e, k=kind: self._rebuild_heater_table(k))
        spin.bind("<Return>", lambda _e, k=kind: self._rebuild_heater_table(k))
        self._heater_table_frames[kind + "_header"] = header
        self._rebuild_heater_table(kind)

    def _capture_heater_values(self, kind: str) -> list[float]:
        values = [0.0] * 9
        for (phase, stage), var in self._heater_table_values.get(kind, {}).items():
            try:
                value = float(var.get().replace(",", ".") or 0)
            except ValueError:
                value = 0.0
            index = {"R": 0, "S": 3, "T": 6}[phase] + (stage - 1)
            if index < len(values):
                values[index] = value
        return values

    def _rebuild_heater_table(self, kind: str) -> None:
        frame = self._heater_table_frames.get(kind)
        if frame is None:
            return
        old_values = self._capture_heater_values(kind)
        try:
            stage_count = max(1, min(3, int(self._heater_stage_vars[kind].get() or 3)))
        except ValueError:
            stage_count = 3
        self._heater_stage_vars[kind].set(str(stage_count))

        header = self._heater_table_frames.get(kind + "_header")
        for child in tuple(frame.winfo_children()):
            if child is not header:
                child.destroy()

        self._heater_table_values[kind] = {}
        ttk.Label(frame, text="Faz / Kademe").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        for col in range(1, stage_count + 1):
            ttk.Label(frame, text=f"Kademe {col}").grid(row=1, column=col, padx=10, pady=5, sticky="w")

        for row, phase in enumerate(("R", "S", "T"), start=2):
            ttk.Label(frame, text=phase).grid(row=row, column=0, padx=10, pady=5, sticky="w")
            for col in range(1, stage_count + 1):
                index = {"R": 0, "S": 3, "T": 6}[phase] + (col - 1)
                var = tk.StringVar(value=str(old_values[index]))
                self._heater_table_values[kind][(phase, col)] = var
                ttk.Entry(frame, textvariable=var, width=12, style="Green.TEntry").grid(
                    row=row, column=col, padx=10, pady=5, sticky="w"
                )

    def _set_module_visibility(self, visibility: dict[str, bool]) -> None:
        mapping = {
            "run_around": "run_around",
            "dx": "dx",
            "change_over": "change_over",
            "humidifier": "humidifier",
            "rotor": "rotor",
        }
        for key, frame_key in mapping.items():
            widgets = self._module_rows.get(frame_key)
            if widgets:
                visible = bool(visibility.get(key, False))
                for widget in widgets:
                    if visible:
                        widget.grid()
                    else:
                        widget.grid_remove()

        for key, frame_key in (
            ("electrical_heater", "electrical"),
            ("pre_electrical_heater", "pre_electrical"),
        ):
            frame = self._heater_table_frames.get(frame_key)
            if frame:
                if visibility.get(key, False):
                    frame.grid()
                else:
                    frame.grid_remove()

    def _read_module_data(self) -> None:
        if not self.state.c600_connected:
            messagebox.showwarning("MODÜLLER", "Önce C600 bağlantısı kurulmalı.", parent=self)
            self._log("MODÜLLER: Veri çekme isteği reddedildi; C600 bağlı değil.", "error")
            return
        self._module_read_button.configure(state="disabled")
        self._log("MODÜLLER: Register değerleri okunuyor...")
        threading.Thread(target=self._module_data_worker, daemon=True).start()

    def _module_data_worker(self) -> None:
        values: dict[str, float] = {}
        error: Exception | None = None
        try:
            for key, point_id in MODULE_REGISTER_POINTS.items():
                result = self._c600_json_read(point_id)
                raw = str(result.get("value", "")).strip().replace(",", ".")
                if not raw:
                    raise ValueError(f"{point_id}: değer boş")
                values[key] = float(raw)
        except Exception as exc:
            error = exc

        def apply() -> None:
            self._module_read_button.configure(state="normal")
            if error is not None:
                self._log(f"MODÜLLER: Register okuma hatası: {error}", "error")
                messagebox.showerror("MODÜLLER", f"Modül verileri okunamadı:\n{error}", parent=self)
                return

            elec = values["electrical_heater"] > 0
            pre_elec = values["pre_electrical_heater"] > 0
            run = int(values["run_around"]) == 1
            dx_count = max(0, int(values["dx_capacity"]))
            dx_visible = dx_count > 0
            cover = int(values["change_over"]) == 1
            hum_count = max(0, int(values["humidifier_capacity"]))
            rotor = int(values["rotor_mode"])

            self.state.electrical_heater = elec
            self.state.electrical_stage_count = 3
            self.state.pre_electrical_heater = pre_elec
            self.state.pre_electrical_stage_count = 3
            self.state.run_around = run
            self.state.dx_enabled = dx_visible
            self.state.dx_stage = dx_count
            self.state.change_over = cover
            self.state.humidifier_enabled = hum_count > 0
            self.state.humidifier_stage = hum_count
            self.state.rotor_enabled = rotor in (1, 2)
            self.state.rotor_mode = {0: "Yok", 1: "Oransal", 2: "On/Off"}.get(rotor, f"Bilinmiyor ({rotor})")

            self._module_vars["rotor"].set(self.state.rotor_mode)
            self._module_vars["run_around"].set("Var" if run else "Yok")
            self._module_vars["dx"].set(str(dx_count))
            self._module_vars["change_over"].set("ChangeOverValve" if cover else "Yok")
            self._module_vars["humidifier"].set(str(hum_count))
            self._heater_stage_vars["electrical"].set("3")
            self._heater_stage_vars["pre_electrical"].set("3")

            self._set_module_visibility({
                "electrical_heater": elec,
                "pre_electrical_heater": pre_elec,
                "run_around": run,
                "dx": dx_visible,
                "change_over": cover,
                "humidifier": hum_count > 0,
                "rotor": rotor in (1, 2),
            })
            self._rebuild_heater_table("electrical")
            self._rebuild_heater_table("pre_electrical")
            self._log(
                "MODÜLLER: "
                f"ELECHEATERENB={values['electrical_heater']}, "
                f"PREELECHEATEREN={values['pre_electrical_heater']}, "
                f"RUNAROUNDENB={values['run_around']}, "
                f"DXCAPACITY={values['dx_capacity']}, "
                f"COVERCONTSELECT={values['change_over']}, "
                f"HUMIFIERCAPACIT={values['humidifier_capacity']}, "
                f"ROTORCONTSELECT={values['rotor_mode']}",
                "ok",
            )
            self._update_statuses()

        self._c600_ui(apply)

    def _save_module_state(self) -> None:
        self.state.electrical_stage_count = max(1, min(3, int(self._heater_stage_vars["electrical"].get() or 3)))
        self.state.pre_electrical_stage_count = max(1, min(3, int(self._heater_stage_vars["pre_electrical"].get() or 3)))
        self.state.electrical_values = self._capture_heater_values("electrical")
        self.state.pre_electrical_values = self._capture_heater_values("pre_electrical")
        self._update_statuses()

    def _add_user_report(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook)
        notebook.add(tab, text="Rapor")
        card = ttk.LabelFrame(body, text="Rapor", style="Card.TLabelframe", padding=14)
        card.pack(fill="x")
        ttk.Label(card, text="Kullanıcı").grid(row=0, column=0, sticky="w", pady=6)
        self._user_var = tk.StringVar(value="")
        ttk.Entry(card, textvariable=self._user_var, width=40).grid(row=0, column=1, sticky="w", pady=6)
        ttk.Button(card, text="Kaydet", style="Primary.TButton", command=self._save).grid(row=1, column=0, sticky="w", pady=(12, 0))
        ttk.Button(
            card,
            text="Test Raporu Oluştur",
            style="Primary.TButton",
            command=self._generate_test_report,
        ).grid(row=2, column=0, sticky="w", pady=(12, 0))

    def _build_bottom_dock(self) -> None:
        dock = ttk.Frame(self, style="White.TFrame", padding=(10, 6))
        dock.pack(side="bottom", fill="x", padx=10, pady=(6, 0))
        ttk.Button(dock, text="↻ Temizle", style="Secondary.TButton", command=self._clear).pack(side="left", padx=3)
        ttk.Button(dock, text="▣ Rapor", style="Secondary.TButton", command=self._report).pack(side="left", padx=3)

    def _log(self, message: str, tag: str = "muted") -> None:
        """Write every user-visible operation to the central process log."""
        writer = getattr(self, "_c600_log_write", None)
        if writer:
            writer(message, tag)

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

    def _save_fan_and_unlock_damper(self) -> None:
        """Save Fan Control fields and then reveal the Damper Control tab."""
        try:
            # Fan tipi ve adetleri artık registerlardan otomatik belirlenir.
            if hasattr(self, "_aspirator_fan_type_var"):
                self.state.fan_type = (
                    f"Aspiratör: {self._aspirator_fan_type_var.get()} | "
                    f"Vantilatör: {self._ventilator_fan_type_var.get()}"
                )
                self.state.supply_fan_count = int(self._ventilator_fan_count_var.get() or 0)
                self.state.return_fan_count = int(self._aspirator_fan_count_var.get() or 0)
            self.state.supply_airflow = self._supply_airflow_var.get()
            self.state.return_airflow = self._return_airflow_var.get()
            self._update_statuses()
            self._log(
                f"FAN KONTROL: KAYDET — fan={self.state.fan_type}, supply_fan={self.state.supply_fan_count}, return_fan={self.state.return_fan_count}, supply_airflow={self.state.supply_airflow}, return_airflow={self.state.return_airflow}",
                "ok",
            )
            self._set_tab_visible("Damper Kontrol", True)
            self._log("İŞ AKIŞI: DAMPER KONTROL sekmesi açıldı.", "ok")
        except (TypeError, ValueError) as exc:
            messagebox.showwarning("FAN KONTROL", f"Fan bilgileri kontrol edilmeli:\n{exc}", parent=self)

    def _save_and_unlock(self, tab_name: str) -> None:
        """Save the current page and explicitly unlock its next workflow tab."""
        self._save()
        self._log(f"{self.tabs.tab(self.tabs.select(), 'text')}: KAYDET", "ok")
        self._set_tab_visible(tab_name, True)
        self._log(f"İŞ AKIŞI: {tab_name} sekmesi açıldı.", "ok")

    def _unlock_next_tab_after_save(self) -> None:
        """Unlock the next tab according to the fixed workflow order."""
        current = self.tabs.tab(self.tabs.select(), "text")
        next_tabs = {
            "Fan Kontrol": "Damper Kontrol",
            "Damper Kontrol": "Filtre Kontrol",
            "Filtre Kontrol": "Modüller",
            "Modüller": "Sensörler",
            "Sensörler": "Rapor",
        }
        next_tab = next_tabs.get(current)
        if next_tab:
            self._set_tab_visible(next_tab, True)

    def _save(self) -> None:
        self.state.order_no = self._order_no_var.get()
        self.state.project_name = self._project_name_var.get()
        self.state.ahu_name = self._ahu_name_var.get()
        if hasattr(self, "_aspirator_fan_type_var"):
            self.state.fan_type = (
                f"Aspiratör: {self._aspirator_fan_type_var.get()} | "
                f"Vantilatör: {self._ventilator_fan_type_var.get()}"
            )
            self.state.supply_fan_count = int(self._ventilator_fan_count_var.get() or 0)
            self.state.return_fan_count = int(self._aspirator_fan_count_var.get() or 0)
        self.state.supply_airflow = self._supply_airflow_var.get()
        self.state.return_airflow = self._return_airflow_var.get()
        self._save_damper_state()
        for name, var in self._filter_vars.items():
            self.state.filters[name] = var.get()
        self._save_module_state()
        self._save_sensor_state()
        self.state.user_name = self._user_var.get()
        self._update_statuses()

    def _clear(self) -> None:
        self.state = TestControlState()
        for attr in ("order_no", "project_name", "ahu_name"):
            getattr(self, f"_{attr}_var").set("")
        if hasattr(self, "_aspirator_fan_type_var"):
            self._aspirator_fan_type_var.set("Yok")
            self._aspirator_fan_count_var.set("0")
            self._ventilator_fan_type_var.set("Yok")
            self._ventilator_fan_count_var.set("0")
        self._supply_airflow_var.set(self.state.supply_airflow)
        self._return_airflow_var.set(self.state.return_airflow)
        self._airflow_var.set(self.state.airflow_control_ok)
        self._pressure_var.set(self.state.pressure_control_ok)
        self._clear_damper_ui()
        for name, var in self._filter_vars.items():
            var.set(str(self.state.filters[name]))
        if hasattr(self, "_module_vars"):
            self._module_vars["rotor"].set("Yok")
            self._module_vars["run_around"].set("Yok")
            self._module_vars["dx"].set("0")
            self._module_vars["change_over"].set("Yok")
            self._module_vars["humidifier"].set("0")
            self._heater_stage_vars["electrical"].set("3")
            self._heater_stage_vars["pre_electrical"].set("3")
            self._rebuild_heater_table("electrical")
            self._rebuild_heater_table("pre_electrical")
            self._set_module_visibility({
                "electrical_heater": False,
                "pre_electrical_heater": False,
                "run_around": False,
                "dx": False,
                "change_over": False,
                "humidifier": False,
                "rotor": True,
            })
        self._clear_sensor_ui()
        self._user_var.set("")
        self._update_statuses()

    def _generate_test_report(self) -> None:
        try:
            self._save()
            path = save_report_dialog(self, self.state)
            if path:
                self._log(f"RAPOR: test raporu oluşturuldu — {path}", "ok")
                messagebox.showinfo("RAPOR", f"Test raporu oluşturuldu:\n{path}", parent=self)
        except Exception as exc:
            self._log(f"RAPOR: PDF oluşturma hatası: {exc}", "error")
            messagebox.showerror("RAPOR", f"Test raporu oluşturulamadı:\n{exc}", parent=self)

    def _report(self) -> None:
        self._generate_test_report()

if __name__ == "__main__":
    TestControlApp().mainloop()
