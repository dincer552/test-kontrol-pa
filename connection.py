from __future__ import annotations

import base64
import json
import socket
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
import urllib.parse
import urllib.request


C600_API_USERNAME = "ADMIN"
C600_API_PASSWORD = "SBTAdmin!"
C600_API_PIN = "6000"


class C600ConnectionMixin:
    """C600 / Climatix BAĞLANTI tab and JSON API integration."""

    def _init_connection_state(self) -> None:
        self._c600_status_var = tk.StringVar(value="Bağlanmadı")
        self._c600_socket: socket.socket | None = None
        self._c600_tx_id = 0
        self._c600_log: tk.Text | None = None
        self._c600_info_vars: dict[str, tk.StringVar] = {}

    def _add_c600(self, notebook: ttk.Notebook) -> None:
        tab, body = self._tab_frame(notebook)
        notebook.add(tab, text="BAĞLANTI")
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
        self._c600_test_btn = ttk.Button(buttons, text="BAĞLAN", style="Primary.TButton", command=self._c600_test)
        self._c600_test_btn.pack(side="left")

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
                self._read_sensors_from_plc()
                self._update_statuses()
                self._on_c600_connection_success()
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

        # The embedded Climatix web server expects spaces in IDs as %20.
        # urllib.parse.urlencode() uses '+' for spaces, which works with normal
        # web servers but is not handled correctly by this C600 endpoint.
        query = (
            f"fn=Read&pin={urllib.parse.quote(C600_API_PIN, safe='')}"
            f"&lng=0&us=2&id={urllib.parse.quote(point_id, safe='')}"
        )
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

            model = str(results["model"].get("value", "—")).strip() or "—"
            serial = str(results["serial"].get("value", "—")).strip() or "—"
            firmware = str(results["firmware"].get("value", "—")).strip() or "—"
            revision = str(results["revision"].get("value", "—")).strip() or "—"

            # Identity information is independent of the optional clock points.
            # Do not hide valid device information if a clock point is unavailable.
            def update_identity() -> None:
                self._c600_info_vars["model"].set(model)
                self._c600_info_vars["serial"].set(serial)
                self._c600_info_vars["firmware"].set(firmware)
                self._c600_info_vars["revision"].set(revision)
                self._c600_log_write(f"Model: {model}", "ok")
                self._c600_log_write(f"Serial No: {serial}", "ok")
                self._c600_log_write(f"Firmware: {firmware}", "ok")
                self._c600_log_write(f"Revision: {revision}", "ok")

            self._c600_ui(update_identity)

            clock_values: list[str] = []
            clock_errors: list[str] = []
            for point_id in ("1-SYSTEM CLOCK", "2-SYSTEM CLOCK", "3-SYSTEM CLOCK"):
                value = ""
                last_error: Exception | None = None
                for attempt in range(3):
                    try:
                        result = self._c600_json_read(point_id)
                        value = str(result.get("value", "")).strip()
                        if value:
                            break
                    except Exception as exc:
                        last_error = exc
                    time.sleep(0.4)
                if value:
                    clock_values.append(value)
                    self._c600_ui(lambda pid=point_id, val=value: self._c600_log_write(f"{pid}: {val}", "muted"))
                elif last_error is not None:
                    clock_errors.append(f"{point_id}: {last_error}")

            if len(clock_values) == 3:
                try:
                    hour = int(float(clock_values[0]))
                    minute = int(float(clock_values[1]))
                    second = int(float(clock_values[2]))
                    clock = f"{hour:02d}:{minute:02d}:{second:02d}"
                except ValueError:
                    clock = " / ".join(clock_values)
            else:
                clock = " / ".join(clock_values) if clock_values else "—"
            self._c600_ui(lambda: self._c600_info_vars["clock"].set(clock))
            if clock_errors:
                self._c600_ui(lambda: self._c600_log_write("Cihaz saati okunamadı; cihaz bilgileri başarıyla okundu.", "muted"))
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
