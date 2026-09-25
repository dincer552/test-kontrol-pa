"""GitHub Release updater for the packaged Test Kontrol Windows application.

The EXE is downloaded from the latest GitHub Release in 2 MiB parts.
There is no SHA-256, digest, manifest, or chunk hash verification.
Each small part is simply downloaded completely and then all parts are
joined in order into the final EXE. If a part is cut off by the network,
only that part is downloaded again.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from tkinter import messagebox

from build_info import BUILD_VERSION

REPO = "dincer552/test-kontrol-pa"
API_URL = f"https://api.github.com/repos/{REPO}/releases/tags/latest"
USER_AGENT = "Test-Kontrol-Updater"
PART_RE = re.compile(r"^Test_Kontrol_latest\.part(\d+)$")


def check_for_update(current_exe=None) -> dict:
    """Read the latest GitHub Release so the UI can show its actual build version."""
    request = urllib.request.Request(
        API_URL,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
            "Cache-Control": "no-cache",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)

    version = str(payload.get("tag_name") or "").strip()
    if not version:
        raise RuntimeError("GitHub Release sürümü okunamadı.")

    return {
        "available": True,
        "version": version,
        "build": version,
        "size": 0,
        "sha256": "",
        "file": "Test_Kontrol_latest.exe",
        "chunks": [],
    }

def _release_parts() -> list[dict]:
    request = urllib.request.Request(
        API_URL,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
            "Cache-Control": "no-cache",
        },
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)

    parts = []
    for asset in payload.get("assets", []):
        name = asset.get("name", "")
        match = PART_RE.match(name)
        if not match:
            continue
        parts.append(
            {
                "name": name,
                "number": int(match.group(1)),
                "size": int(asset.get("size", 0)),
                "url": asset.get("browser_download_url", ""),
            }
        )

    parts.sort(key=lambda item: item["number"])

    if not parts:
        raise RuntimeError("GitHub Release içinde güncelleme parçaları bulunamadı.")

    return parts


def _download_part(part: dict, folder: Path, progress=None, done_before: int = 0, total: int = 0) -> Path:
    target = folder / part["name"]
    expected = part["size"]

    for attempt in range(1, 9):
        downloaded = 0
        try:
            request = urllib.request.Request(
                part["url"],
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/octet-stream",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                    "Accept-Encoding": "identity",
                },
            )

            with urllib.request.urlopen(request, timeout=120) as response:
                with target.open("wb") as output:
                    while True:
                        data = response.read(256 * 1024)
                        if not data:
                            break
                        output.write(data)
                        downloaded += len(data)

                        if progress:
                            speed = (done_before + downloaded) / max(time.monotonic() - progress.start_time, 0.001)
                            progress(done_before + downloaded, total, speed)

            if expected and downloaded != expected:
                target.unlink(missing_ok=True)
                if attempt == 8:
                    raise RuntimeError(
                        f"{part['name']} eksik indirildi ({downloaded:,} / {expected:,} byte)."
                    )
                time.sleep(min(attempt, 5))
                continue

            return target

        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            target.unlink(missing_ok=True)
            if attempt == 8:
                raise RuntimeError(
                    f"{part['name']} indirilemedi: {exc}"
                ) from exc
            time.sleep(min(attempt, 5))

    raise RuntimeError(f"{part['name']} indirilemedi.")


def _download_latest(progress=None) -> Path:
    """Download 2 MiB GitHub Release parts and join them into one EXE."""
    temp_dir = Path(tempfile.mkdtemp(prefix="test_kontrol_update_"))
    target = temp_dir / "Test_Kontrol_update.exe"

    try:
        parts = _release_parts()
        total = sum(part["size"] for part in parts)
        done = 0

        if progress:
            progress.start_time = time.monotonic()

        part_files = []
        for part in parts:
            part_file = _download_part(
                part,
                temp_dir,
                progress=progress,
                done_before=done,
                total=total,
            )
            part_files.append(part_file)
            done += part["size"]

        with target.open("wb") as output:
            for part_file in part_files:
                with part_file.open("rb") as source:
                    while True:
                        data = source.read(1024 * 1024)
                        if not data:
                            break
                        output.write(data)

        if not target.exists() or target.stat().st_size != total:
            raise RuntimeError("Güncelleme dosyası birleştirilemedi.")

        return target

    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"GitHub güncelleme sunucusu HTTP {exc.code}: {exc.reason}"
        ) from exc
    finally:
        # Keep the completed EXE until the PowerShell replacement process moves it.
        if not target.exists():
            for item in temp_dir.glob("*"):
                item.unlink(missing_ok=True)
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
    """Download the latest GitHub Release in small parts and install it."""
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
