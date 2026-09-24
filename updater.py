"""Self-updater for the packaged Test Kontrol Windows application.

The update flow mirrors the PDF kW Selector updater:
- read a manifest from the VM,
- download 256 KB chunks in parallel with retries,
- verify total size and SHA-256,
- replace the running EXE from a helper process after exit,
- close the old application after installation and ask the user to restart it manually.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from tkinter import messagebox

from build_info import BUILD_SHA, BUILD_VERSION

UPDATE_MANIFEST_URL = "http://20.91.245.7/pdf-updates/test-kontrol/manifest.json"
USER_AGENT = "Test-Kontrol-Updater"


def _cache_busted(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("_cache", str(time.time_ns())))
    return urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(query)))


def _get_json(url: str) -> dict:
    request = urllib.request.Request(
        _cache_busted(url),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Güncelleme sunucusu HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Güncelleme sunucusuna bağlanılamadı: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Güncelleme manifesti geçerli JSON değil.") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def _version_tuple(version: str | None) -> tuple[int, ...]:
    text = str(version or "").strip().lstrip("vV")
    parts = text.split(".")
    try:
        return tuple(int(part) for part in parts if part != "")
    except ValueError:
        return ()


def _manifest_chunk_url(file_name: str) -> str:
    if file_name.startswith("http://") or file_name.startswith("https://"):
        return file_name
    return urllib.parse.urljoin(UPDATE_MANIFEST_URL, file_name.lstrip("/"))


def check_for_update(current_exe: Path | None = None) -> dict:
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Güncelleme yalnızca paketlenmiş Windows EXE içinde kullanılabilir.")

    current = Path(current_exe or sys.executable).resolve()
    manifest = _get_json(UPDATE_MANIFEST_URL)

    remote_version = str(manifest.get("version") or "").strip() or "latest"
    remote_build = str(manifest.get("build") or "").strip().lower()
    remote_sha = str(manifest.get("sha256") or "").replace("sha256:", "").lower()
    current_sha = _sha256(current) if current.exists() else ""

    same_build = bool(remote_build and BUILD_SHA and remote_build == str(BUILD_SHA).lower())
    same_digest = bool(remote_sha and current_sha and remote_sha == current_sha)
    current_version_tuple = _version_tuple(BUILD_VERSION)
    remote_version_tuple = _version_tuple(remote_version)
    same_or_newer_version = bool(current_version_tuple and remote_version_tuple) and current_version_tuple >= remote_version_tuple

    available = not (same_build or same_digest or same_or_newer_version)

    chunks = []
    for chunk in manifest.get("chunks") or []:
        file_name = str(chunk.get("file") or "").strip()
        size = int(chunk.get("size") or 0)
        if not file_name or size <= 0:
            raise RuntimeError("Güncelleme manifestindeki parça bilgisi geçersiz.")
        chunks.append({"url": _manifest_chunk_url(file_name), "size": size})

    return {
        "available": available,
        "version": remote_version,
        "build": remote_build,
        "size": int(manifest.get("size") or 0),
        "sha256": remote_sha,
        "file": str(manifest.get("file") or "Test_Kontrol_latest.exe"),
        "chunks": chunks,
        "current_exe": current,
        "current_sha256": current_sha,
    }


def _download_chunk(url: str, expected_size: int, index: int) -> tuple[int, bytes]:
    last_size = 0
    last_error: Exception | None = None
    for attempt in range(1, 6):
        try:
            request = urllib.request.Request(
                _cache_busted(url),
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/octet-stream",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                    "Accept-Encoding": "identity",
                },
            )
            with urllib.request.urlopen(request, timeout=180) as response:
                data = response.read()
            last_size = len(data)
            if last_size == expected_size:
                return index, data
            last_error = RuntimeError(f"{last_size}/{expected_size} bayt")
        except Exception as exc:
            last_error = exc
        if attempt < 5:
            time.sleep(0.5 * attempt)

    raise RuntimeError(
        f"Güncelleme parçası {index + 1} indirilemedi ({last_size}/{expected_size} bayt)."
    ) from last_error


def download_update(update: dict, progress=None) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="test_kontrol_update_"))
    target = temp_dir / "Test_Kontrol_update.exe"
    chunks = list(update.get("chunks") or [])

    try:
        if chunks:
            total = sum(int(chunk["size"]) for chunk in chunks)
            downloaded = 0
            pending: dict[int, bytes] = {}
            next_index = 0
            started_at = time.monotonic()
            with target.open("wb") as output:
                with ThreadPoolExecutor(max_workers=4, thread_name_prefix="test-kontrol-update") as executor:
                    futures = [
                        executor.submit(_download_chunk, chunk["url"], int(chunk["size"]), index)
                        for index, chunk in enumerate(chunks)
                    ]
                    for future in as_completed(futures):
                        index, data = future.result()
                        pending[index] = data
                        while next_index in pending:
                            ordered = pending.pop(next_index)
                            output.write(ordered)
                            downloaded += len(ordered)
                            next_index += 1
                            if progress:
                                speed = downloaded / max(time.monotonic() - started_at, 0.001)
                                progress(downloaded, total, speed)
        else:
            url = _manifest_chunk_url(str(update["file"]))
            expected_size = int(update.get("size") or 0)
            request = urllib.request.Request(
                _cache_busted(url),
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/octet-stream",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                    "Accept-Encoding": "identity",
                },
            )
            with urllib.request.urlopen(request, timeout=180) as response, target.open("wb") as output:
                while True:
                    data = response.read(1024 * 1024)
                    if not data:
                        break
                    output.write(data)

        actual_size = target.stat().st_size
        expected_size = int(update.get("size") or 0)
        if expected_size and actual_size != expected_size:
            raise RuntimeError(f"Güncelleme boyutu hatalı: {actual_size}/{expected_size} bayt")

        expected_sha = str(update.get("sha256") or "").replace("sha256:", "").lower()
        actual_sha = _sha256(target)
        if expected_sha and actual_sha != expected_sha:
            raise RuntimeError(
                "Güncelleme SHA-256 doğrulaması başarısız oldu: "
                f"beklenen {expected_sha}, alınan {actual_sha}."
            )
        return target
    except Exception:
        target.unlink(missing_ok=True)
        try:
            temp_dir.rmdir()
        except OSError:
            pass
        raise


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
            # PowerShell Move-Item -Force does not reliably replace an existing
            # Windows executable. Remove the old EXE after the parent process
            # has exited, then move the verified download into its place.
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
        "Güncelleme kurulamadı.`n`n$($_.Exception.Message)",
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
    """Check the VM manifest, download and verify the new EXE, then ask for a manual restart."""
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
            update = check_for_update(current)
            if not update["available"]:
                parent.after(0, lambda: messagebox.showinfo("GÜNCELLE", f"Program zaten güncel.\nSürüm: {BUILD_VERSION}", parent=parent))
                finish()
                return

            size_mb = update["size"] / (1024 * 1024) if update["size"] else 0
            confirmed = {"ok": False}

            def ask() -> None:
                confirmed["ok"] = messagebox.askyesno(
                    "GÜNCELLE",
                    f"Yeni sürüm bulundu: {update['version']}\nBoyut: {size_mb:.1f} MB\n\nVM üzerinden güncelleme indirilsin mi?",
                    parent=parent,
                )

            parent.after(0, ask)
            while not confirmed["ok"] and getattr(parent, "_update_running", False):
                time.sleep(0.05)

            if not confirmed["ok"]:
                finish()
                return

            parent.after(0, lambda: set_button("İNDİRİLİYOR...", False))

            def report(done: int, total: int, speed: float) -> None:
                percent = int(done * 100 / total) if total else 0
                mb = done / (1024 * 1024)
                total_mb = total / (1024 * 1024) if total else 0
                parent.after(0, lambda: set_button(f"İNDİR {percent}%", False))
                parent.after(0, lambda: parent.title(f"TEST KONTROL — Güncelleme {percent}% ({mb:.1f}/{total_mb:.1f} MB, {speed / (1024 * 1024):.1f} MB/s)"))

            downloaded = download_update(update, progress=report)
            parent.after(0, lambda: parent.title(f"TEST KONTROL {update['version']} — Güncelleme hazırlanıyor..."))
            _start_replacement(downloaded, current)
            parent.after(250, lambda: messagebox.showinfo(
                "GÜNCELLEME HAZIR",
                "Güncelleme başarıyla kuruldu.\n\nTEST KONTROL kapatıldı. Değişikliklerin uygulanması için programı yeniden başlatın.",
                parent=parent,
            ))
            parent.after(300, parent.destroy)
        except Exception as exc:
            parent.after(0, lambda: messagebox.showerror("GÜNCELLE", f"Güncelleme başarısız:\n{exc}", parent=parent))
            finish()

    parent.after(0, lambda: set_button("KONTROL...", False))
    threading.Thread(target=worker, name="test-kontrol-updater", daemon=True).start()
