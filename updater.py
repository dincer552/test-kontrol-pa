"""Simple GitHub-based updater for the packaged Test Kontrol Windows application.

Updates are downloaded directly from the latest GitHub Release.
No VM manifest, SHA-256 verification, chunk verification, or digest comparison
is used. The download is only accepted when the HTTP Content-Length matches
the number of bytes actually received.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from tkinter import messagebox

from build_info import BUILD_VERSION

UPDATE_URL = (
    "https://github.com/dincer552/test-kontrol-pa/"
    "releases/latest/download/Test_Kontrol_latest.exe"
)
USER_AGENT = "Test-Kontrol-Updater"


def check_for_update(current_exe=None) -> dict:
    """Keep the existing app UI compatible while using direct GitHub downloads."""
    return {
        "available": True,
        "version": "latest",
        "build": "",
        "size": 0,
        "sha256": "",
        "file": "Test_Kontrol_latest.exe",
        "chunks": [],
    }


def _download_latest(progress=None) -> Path:
    """Download the GitHub asset with HTTP Range resume support.

    No SHA/manifest verification is performed. If the connection is cut
    before EOF, the next request resumes from the exact byte already saved.
    This handles networks/proxies that terminate large downloads early.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="test_kontrol_update_"))
    target = temp_dir / "Test_Kontrol_update.exe"

    total = 0
    downloaded = 0
    started_at = time.monotonic()
    max_attempts = 30

    try:
        with target.open("wb") as output:
            for attempt in range(1, max_attempts + 1):
                request = urllib.request.Request(
                    UPDATE_URL,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "application/octet-stream",
                        "Cache-Control": "no-cache",
                        "Pragma": "no-cache",
                        "Accept-Encoding": "identity",
                    },
                )
                if downloaded:
                    request.add_header("Range", f"bytes={downloaded}-")

                try:
                    with urllib.request.urlopen(request, timeout=180) as response:
                        status = getattr(response, "status", response.getcode())

                        content_range = response.headers.get("Content-Range", "")
                        if content_range:
                            try:
                                total = int(content_range.rsplit("/", 1)[1])
                            except (ValueError, IndexError):
                                pass

                        content_length = response.headers.get("Content-Length")
                        if not total and content_length and content_length.isdigit():
                            if status == 206 and downloaded:
                                total = downloaded + int(content_length)
                            else:
                                total = int(content_length)

                        if downloaded and status != 206:
                            raise RuntimeError(
                                "Sunucu devam indirmesini desteklemedi (HTTP Range)."
                            )

                        while True:
                            data = response.read(1024 * 1024)
                            if not data:
                                break
                            output.write(data)
                            downloaded += len(data)

                            if progress:
                                speed = downloaded / max(time.monotonic() - started_at, 0.001)
                                progress(downloaded, total, speed)

                except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
                    if attempt >= max_attempts:
                        raise RuntimeError(
                            f"GitHub indirmesi bağlantı nedeniyle tamamlanamadı: {exc}"
                        ) from exc
                    time.sleep(min(2 + attempt, 10))
                    continue

                if total and downloaded >= total:
                    break

                if not total:
                    raise RuntimeError(
                        "GitHub indirme boyutu alınamadı; dosya güvenli şekilde tamamlanamıyor."
                    )

                time.sleep(1)

        if not target.exists() or downloaded <= 0:
            raise RuntimeError("GitHub'dan güncelleme dosyası indirilemedi.")

        if total and downloaded != total:
            raise RuntimeError(
                f"Güncelleme eksik indirildi ({downloaded:,} / {total:,} byte). "
                "Mevcut program korunuyor."
            )

        return target

    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"GitHub güncelleme sunucusu HTTP {exc.code}: {exc.reason}"
        ) from exc
    except Exception:
        raise
    finally:
        if not target.exists() or (total and downloaded != total):
            target.unlink(missing_ok=True)
            try:
                temp_dir.rmdir()
            except OSError:
                pass


def _start_replacement(downloaded: Path, current_exe: Path) -> None:
    script = Path(tempfile.gettempdir()) / f"test_kontrol_update_{os.getpid()}_{time.time_ns()}.ps1"
    script.write_text(
        r"""
param([string]$Source, [string]$Target, [int]$ParentPid, [string]$ScriptPath)
$ErrorActionPreference = "Stop"
try {
    for ($i = 0; $i -lt 120; $i++) {
        if (-not (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 250
    }
    if (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue) {
        throw "Eski program kapatılamadı."
    }

    for ($i = 0; $i -lt 60; $i++) {
        try {
            if (Test-Path -LiteralPath $Target) {
                Remove-Item -LiteralPath $Target -Force -ErrorAction Stop
            }
            Move-Item -LiteralPath $Source -Destination $Target -Force -ErrorAction Stop
            break
        } catch {
            if ($i -eq 59) { throw }
            Start-Sleep -Seconds 1
        }
    }

    if (-not (Test-Path -LiteralPath $Target)) {
        throw "Güncelleme dosyası hedefe taşınamadı."
    }
} catch {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        ("Güncelleme kurulamadı." + [Environment]::NewLine + [Environment]::NewLine + $_.Exception.Message),
        "TEST KONTROL - Güncelleme",
        [System.Windows.MessageBoxButton]::OK,
        [System.Windows.MessageBoxImage]::Error
    ) | Out-Null
} finally {
    Remove-Item -LiteralPath $ScriptPath -Force -ErrorAction SilentlyContinue
}
""".strip(),
        encoding="utf-8-sig",
    )

    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Source",
            str(downloaded),
            "-Target",
            str(current_exe),
            "-ParentPid",
            str(os.getpid()),
            "-ScriptPath",
            str(script),
        ],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def start_update(parent, button=None) -> None:
    """Download the latest GitHub Release directly and install it."""
    if getattr(parent, "_update_running", False):
        return

    parent._update_running = True
    if button is None:
        button = getattr(parent, "_update_button", None)

    def set_button(text: str, enabled: bool) -> None:
        if button is None:
            return
        try:
            button.configure(text=text, state="normal" if enabled else "disabled")
        except Exception:
            pass

    def finish() -> None:
        parent._update_running = False
        parent.after(0, lambda: set_button("GÜNCELLE", True))

    def worker() -> None:
        try:
            current = Path(sys.executable).resolve()

            parent.after(0, lambda: set_button("İNDİRİLİYOR...", False))

            def report(done: int, total: int, speed: float) -> None:
                percent = int(done * 100 / total) if total else 0
                mb = done / (1024 * 1024)
                total_mb = total / (1024 * 1024) if total else 0
                parent.after(0, lambda: set_button(f"İNDİR {percent}%", False))
                parent.after(
                    0,
                    lambda: parent.title(
                        f"TEST KONTROL — Güncelleme {percent}% "
                        f"({mb:.1f}/{total_mb:.1f} MB, {speed / (1024 * 1024):.1f} MB/s)"
                    ),
                )

            downloaded = _download_latest(progress=report)

            parent.after(
                0,
                lambda: parent.title("TEST KONTROL — Güncelleme hazırlanıyor..."),
            )

            _start_replacement(downloaded, current)

            parent.after(
                250,
                lambda: messagebox.showinfo(
                    "GÜNCELLEME HAZIR",
                    "Güncelleme indirildi ve kuruluma hazırlandı.\n\n"
                    "TEST KONTROL kapatıldı. Değişikliklerin uygulanması için "
                    "programı yeniden başlatın.",
                    parent=parent,
                ),
            )
            parent.after(300, parent.destroy)

        except Exception as exc:
            parent.after(
                0,
                lambda: messagebox.showerror(
                    "GÜNCELLE",
                    f"Güncelleme başarısız:\n{exc}",
                    parent=parent,
                ),
            )
            finish()

    parent.after(0, lambda: set_button("KONTROL...", False))
    threading.Thread(
        target=worker,
        name="test-kontrol-updater",
        daemon=True,
    ).start()
