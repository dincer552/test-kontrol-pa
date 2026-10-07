from __future__ import annotations

import os
import shutil
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time


class TcpTunnelManager:
    """Manage Siemens RainbowTcpTunnel for direct Climatix TCP/IP access."""

    local_host = "127.0.0.1"
    local_port = 4243
    remote_port = 80
    scope_port = 4242

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._target_host = ""
        self.last_diagnostics = ""

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _communication_dir(self) -> Path:
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        return base / "Communication"

    def _tunnel_exe(self) -> Path:
        bundled = self._communication_dir() / "RainbowTcpTunnel.exe"
        if bundled.exists():
            return bundled

        found = shutil.which("RainbowTcpTunnel.exe")
        if found:
            return Path(found)

        candidates: list[Path] = []
        roots = (
            Path(r"C:\Program Files\Siemens"),
            Path(r"C:\Program Files (x86)\Siemens"),
        )
        for root in roots:
            if not root.exists():
                continue
            try:
                candidates.extend(root.rglob("RainbowTcpTunnel.exe"))
            except OSError:
                continue

        valid = [
            path for path in candidates
            if (path.parent / "RainbowTcpTunnelSrv.dll").exists()
            and (path.parent / "CommandLine.dll").exists()
        ]
        if valid:
            return max(valid, key=lambda path: path.stat().st_mtime)

        if candidates:
            return max(candidates, key=lambda path: path.stat().st_mtime)

        raise FileNotFoundError(
            "RainbowTcpTunnel.exe bulunamadı. Siemens SCOPE/Communication kurulumu gerekli."
        )

    def _log_directory(self) -> Path:
        return Path(os.environ.get("TEMP", tempfile.gettempdir())) / "Rainbow"

    def _read_diagnostics(self) -> str:
        lines: list[str] = []
        for name in ("TunnelError.log", "Tunnel.log"):
            path = self._log_directory() / name
            if not path.exists():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if text.strip():
                tail = text.strip().splitlines()[-12:]
                lines.append(
                    f"{name}: " + " | ".join(line.strip() for line in tail if line.strip())
                )
        return "\n".join(lines)

    def stop(self) -> None:
        process = self._process
        self._process = None
        self._target_host = ""
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

    def _wait_for_listener(self, timeout: float = 12.0) -> None:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self._process is not None and self._process.poll() is not None:
                diagnostics = self._read_diagnostics()
                detail = f"RainbowTcpTunnel kapandı (exit code {self._process.returncode})."
                if diagnostics:
                    detail += f" {diagnostics}"
                raise RuntimeError(detail)
            try:
                with socket.create_connection((self.local_host, self.local_port), timeout=0.4):
                    return
            except OSError as exc:
                last_error = exc
                time.sleep(0.2)

        diagnostics = self._read_diagnostics()
        detail = f"RainbowTcpTunnel {self.local_host}:{self.local_port} portunu açmadı: {last_error}"
        if diagnostics:
            detail += f" {diagnostics}"
        raise TimeoutError(detail)

    def start(self, host: str, target_type: str, auth: str, scope_port: int = 4242) -> None:
        host = host.strip()
        if not host:
            raise ValueError("TCP/IP host boş.")
        try:
            scope_port = int(scope_port)
        except (TypeError, ValueError) as exc:
            raise ValueError("SCOPE portu geçersiz.") from exc
        if not 1 <= scope_port <= 65535:
            raise ValueError("SCOPE portu 1-65535 arasında olmalı.")

        self.stop()
        self.last_diagnostics = ""

        exe = self._tunnel_exe()
        communication_dir = exe.parent
        interface_parameters = f"{host},{auth}"

        args = [
            str(exe),
            "--Port", str(self.local_port),
            "--RemotePort", str(self.remote_port),
            "--TargetType", target_type,
            "--InterfaceType", "TCP/IP",
            "--InterfaceParameters", interface_parameters,
            "--IpAddress", self.local_host,
            "--Verbose",
            "--LogHeaders",
        ]

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self._process = subprocess.Popen(
                args,
                cwd=str(communication_dir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
        except OSError as exc:
            self._process = None
            raise RuntimeError(f"RainbowTcpTunnel başlatılamadı: {exc}") from exc

        self._target_host = host

        def drain_output() -> None:
            process = self._process
            if process is None or process.stdout is None:
                return
            try:
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        self.last_diagnostics = (self.last_diagnostics + " | " + line)[-4000:]
            except Exception:
                pass

        threading.Thread(target=drain_output, daemon=True).start()

        try:
            # The user-entered endpoint is the real SCOPE TCP/IP service.
            # Verify it before waiting for the local forwarding socket.
            with socket.create_connection((host, scope_port), timeout=3.0):
                pass
            self._wait_for_listener()
        except Exception as exc:
            diagnostics = self._read_diagnostics()
            if diagnostics:
                self.last_diagnostics = diagnostics
            self.stop()
            detail = str(exc)
            if self.last_diagnostics and self.last_diagnostics not in detail:
                detail += f"\n{self.last_diagnostics}"
            raise RuntimeError(detail) from exc
