from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
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
        raise FileNotFoundError(
            "RainbowTcpTunnel.exe bulunamadı. Communication bileşenleri EXE içine eklenmemiş."
        )

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

    def _wait_for_listener(self, timeout: float = 8.0) -> None:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self._process is not None and self._process.poll() is not None:
                raise RuntimeError(
                    f"RainbowTcpTunnel kapandı (exit code {self._process.returncode})."
                )
            try:
                with socket.create_connection((self.local_host, self.local_port), timeout=0.4):
                    return
            except OSError as exc:
                last_error = exc
                time.sleep(0.2)
        raise TimeoutError(f"RainbowTcpTunnel {self.local_host}:{self.local_port} portunu açmadı: {last_error}")

    def start(self, host: str, target_type: str, auth: str) -> None:
        host = host.strip()
        if not host:
            raise ValueError("TCP/IP host boş.")
        self.stop()

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
        ]

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self._process = subprocess.Popen(
                args,
                cwd=str(communication_dir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except OSError as exc:
            self._process = None
            raise RuntimeError(f"RainbowTcpTunnel başlatılamadı: {exc}") from exc

        self._target_host = host
        try:
            self._wait_for_listener()
        except Exception:
            self.stop()
            raise
