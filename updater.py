"""Self-updater for the packaged Test Kontrol Windows application."""
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
import urllib.request
from tkinter import messagebox

UPDATE_MANIFEST_URL = "http://20.91.245.7/test-kontrol-updates/manifest.json"
USER_AGENT = "Test-Kontrol-Updater"


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def check_for_update(current_exe: Path | None = None) -> dict:
    current = Path(current_exe or sys.executable).resolve()
    manifest = _get_json(UPDATE_MANIFEST_URL)
    remote_sha = str(manifest.get("sha256") or "").replace("sha256:", "").lower()
    current_sha = _sha256(current) if current.exists() else ""
    remote_version = str(manifest.get("version") or "latest")
    available = bool(remote_sha and current_sha and remote_sha != current_sha)
    if not current.exists():
        available = True
    return {
        "available": available,
        "version": remote_version,
        "build": str(manifest.get("build") or ""),
        "size": int(manifest.get("size") or 0),
        "sha256": remote_sha,
        "file": str(manifest.get("file") or "Test_Kontrol_latest.exe"),
        "chunks": list(manifest.get("chunks") or []),
        "manifest_url": UPDATE_MANIFEST_URL,
        "current_exe": current,
        "current_sha256": current_sha,
    }


def _download_url(path_or_url: str) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    return UPDATE_MANIFEST_URL.rsplit("/", 1)[0] + "/" + path_or_url.lstrip("/")


def _download(url: str, target: Path, expected_size: int | None = None) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/octet-stream", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=180) as response, target.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
    if expected_size and target.stat().st_size != expected_size:
        raise RuntimeError(f"İndirilen dosya boyutu hatalı: {target.stat().st_size}/{expected_size} bayt")


def download_update(update: dict, progress=None) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="test_kontrol_update_"))
    target = temp_dir / "Test_Kontrol_update.exe"
    chunks = update.get("chunks") or []

    if chunks:
        with target.open("wb") as output:
            total = sum(int(chunk.get("size") or 0) for chunk in chunks)
            done = 0
            for index, chunk in enumerate(chunks, start=1):
                part_url = _download_url(str(chunk.get("file") or ""))
                part = temp_dir / f"part_{index:03d}"
                _download(part_url, part, int(chunk.get("size") or 0))
                with part.open("rb") as source:
                    while True:
                        data = source.read(1024 * 1024)
                        if not data:
                            break
                        output.write(data)
                        done += len(data)
                        if progress:
                            progress(done, total)
                part.unlink(missing_ok=True)
    else:
        _download(_download_url(update["file"]), target, update.get("size") or None)

    expected_sha = str(update.get("sha256") or "").lower()
    actual_sha = _sha256(target)
    if expected_sha and actual_sha != expected_sha:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"Güncelleme doğrulaması başarısız. SHA-256: {actual_sha}")
    return target


def _start_replacement(downloaded: Path, current_exe: Path) -> None:
    script = Path(tempfile.gettempdir()) / f"test_kontrol_update_{os.getpid()}_{time.time_ns()}.cmd"
    script.write_text(
        "@echo off\r\n"
        "setlocal\r\n"
        f"set PID={os.getpid()}\r\n"
        f"set NEW={downloaded}\r\n"
        f"set TARGET={current_exe}\r\n"
        ":wait\r\n"
        "tasklist /FI \"PID eq %PID%\" | findstr /R /C:\" %PID% \" >nul\r\n"
        "if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait)\r\n"
        "copy /Y \"%NEW%\" \"%TARGET%\" >nul\r\n"
        "if errorlevel 1 (start \"\" \"%NEW%\" & goto cleanup)\r\n"
        "start \"\" \"%TARGET%\"\r\n"
        ":cleanup\r\n"
        "del /F /Q \"%NEW%\" >nul 2>&1\r\n"
        "del /F /Q \"%~f0\" >nul 2>&1\r\n",
        encoding="utf-8",
    )
    subprocess.Popen(["cmd.exe", "/C", str(script)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def start_update(parent) -> None:
    """Check the VM manifest, download the new EXE, replace the running EXE and restart."""
    if getattr(parent, "_update_running", False):
        return
    parent._update_running = True

    def finish() -> None:
        parent._update_running = False

    def worker() -> None:
        try:
            current = Path(sys.executable).resolve()
            update = check_for_update(current)
            if not update["available"]:
                parent.after(0, lambda: (finish(), messagebox.showinfo("GÜNCELLE", f"Program zaten güncel.\nSürüm: {update['version']}", parent=parent)))
                return

            parent.after(0, lambda: parent.title(f"TEST KONTROL — {update['version']} indiriliyor..."))
            downloaded = download_update(update, progress=lambda done, total: parent.after(0, lambda: None))
            parent.after(0, lambda: parent.title(f"TEST KONTROL {update['version']} — Güncelleme hazırlanıyor..."))
            _start_replacement(downloaded, current)
            parent.after(250, parent.destroy)
        except urllib.error.URLError as exc:
            parent.after(0, lambda: (finish(), messagebox.showerror("GÜNCELLE", f"Güncelleme sunucusuna bağlanılamadı:\n{exc}", parent=parent)))
        except Exception as exc:
            parent.after(0, lambda: (finish(), messagebox.showerror("GÜNCELLE", f"Güncelleme başarısız:\n{exc}", parent=parent)))

    threading.Thread(target=worker, name="test-kontrol-updater", daemon=True).start()
