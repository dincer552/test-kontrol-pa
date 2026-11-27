from __future__ import annotations

import os
import re
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
        self.detected_device = ""

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @staticmethod
    def _has_tunnel_files(folder: Path) -> bool:
        required = (
            "RainbowTcpTunnel.exe",
            "RainbowTcpTunnelSrv.dll",
            "CommandLine.dll",
            "log4net.dll",
            "Interop.RAINBOWCOMHANDLERLib.dll",
        )
        return folder.is_dir() and all((folder / name).is_file() for name in required)

    @staticmethod
    def _registry_install_roots() -> list[Path]:
        """Read SCOPE/Rainbow installation locations without relying on a fixed drive."""
        if sys.platform != "win32":
            return []

        import winreg

        roots: list[Path] = []
        views = (
            getattr(winreg, "KEY_WOW64_32KEY", 0),
            getattr(winreg, "KEY_WOW64_64KEY", 0),
        )
        uninstall_paths = (
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        )
        for view in views:
            for uninstall_path in uninstall_paths:
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        uninstall_path,
                        0,
                        winreg.KEY_READ | view,
                    ) as uninstall:
                        count = winreg.QueryInfoKey(uninstall)[0]
                        for index in range(count):
                            try:
                                subkey_name = winreg.EnumKey(uninstall, index)
                                with winreg.OpenKey(uninstall, subkey_name) as item:
                                    display_name, _ = winreg.QueryValueEx(item, "DisplayName")
                                    if not re.search(r"(siemens.*scope|scope.*siemens|rainbow)", str(display_name), re.I):
                                        continue
                                    try:
                                        install_location, _ = winreg.QueryValueEx(item, "InstallLocation")
                                    except OSError:
                                        continue
                                    if install_location:
                                        roots.append(Path(os.path.expandvars(str(install_location))))
                            except OSError:
                                continue
                except OSError:
                    continue

            app_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\RainbowTcpTunnel.exe"
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    app_path,
                    0,
                    winreg.KEY_READ | view,
                ) as key:
                    exe_path, _ = winreg.QueryValueEx(key, "")
                    if exe_path:
                        roots.append(Path(os.path.expandvars(str(exe_path).strip('"'))).parent)
            except OSError:
                pass

        unique: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = os.path.normcase(os.path.abspath(str(root)))
            if key not in seen:
                seen.add(key)
                unique.append(root)
        return unique

    @staticmethod
    def _scope_search_roots() -> list[Path]:
        roots: list[Path] = []
        for variable in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
            value = os.environ.get(variable)
            if value:
                roots.append(Path(value) / "Siemens")
        for variable in ("CommonProgramFiles", "CommonProgramFiles(x86)"):
            value = os.environ.get(variable)
            if value:
                roots.append(Path(value) / "Rainbow")
        roots.extend(TcpTunnelManager._registry_install_roots())

        unique: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = os.path.normcase(os.path.abspath(str(root)))
            if key not in seen:
                seen.add(key)
                unique.append(root)
        return unique

    def _find_installed_tunnel(self) -> Path | None:
        """Find the Rainbow tunnel supplied and registered by the local SCOPE installation."""
        direct = shutil.which("RainbowTcpTunnel.exe")
        if direct:
            candidate = Path(direct)
            if self._has_tunnel_files(candidate.parent):
                return candidate

        candidates: list[Path] = []
        for root in self._scope_search_roots():
            if not root.exists():
                continue
            if root.is_file() and root.name.lower() == "rainbowtcptunnel.exe":
                candidates.append(root)
                continue
            try:
                candidates.extend(
                    path for path in root.rglob("RainbowTcpTunnel.exe")
                    if self._has_tunnel_files(path.parent)
                )
            except (OSError, PermissionError):
                continue

        if not candidates:
            return None
        return max(candidates, key=lambda path: path.stat().st_mtime)

    @staticmethod
    def _is_com_handler_registered() -> bool:
        """Check whether the locally installed SCOPE Rainbow COM server is registered."""
        if sys.platform != "win32":
            return True
        try:
            import winreg

            clsid_root = r"CLSID\{B14C61DD-E5EB-4735-941E-03E400367B2E}"
            views = (
                getattr(winreg, "KEY_WOW64_32KEY", 0),
                getattr(winreg, "KEY_WOW64_64KEY", 0),
            )
            for view in views:
                for server_kind in ("LocalServer32", "InprocServer32"):
                    try:
                        with winreg.OpenKey(
                            winreg.HKEY_CLASSES_ROOT,
                            clsid_root + "\\" + server_kind,
                            0,
                            winreg.KEY_READ | view,
                        ) as key:
                            server, _ = winreg.QueryValueEx(key, "")
                    except OSError:
                        continue
                    match = re.match(r'\s*"([^"]+)"', str(server))
                    server_path = match.group(1) if match else str(server).split(" ", 1)[0]
                    if Path(os.path.expandvars(server_path)).is_file():
                        return True
            return False
        except (OSError, ImportError, ValueError):
            return False

    def _tunnel_exe(self) -> Path:
        installed = self._find_installed_tunnel()
        if installed is not None:
            return installed

        resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        bundled_dir = resource_root / "Communication"
        if self._has_tunnel_files(bundled_dir):
            return bundled_dir / "RainbowTcpTunnel.exe"

        raise FileNotFoundError(
            "Siemens SCOPE/Communication kurulumu bulunamadı. "
            "Bu bilgisayara SCOPE kurun veya kurulumun Communication bileşenini onarın. "
            "Test Kontrol ayrıca Communication.zip indirmez."
        )

    def _log_directory(self) -> Path:
        return Path(os.environ.get("TEMP", tempfile.gettempdir())) / "Rainbow"

    def _read_diagnostics(self) -> str:
        lines: list[str] = []
        lines.append(f"Log dizini: {self._log_directory()}")
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

    def _detect_usb_device(self) -> str:
        """Read the connected Climatix device name from Rainbow diagnostics."""
        pattern = re.compile(r"\b(POL\d+_[A-Z0-9]+)\b", re.IGNORECASE)
        candidates: list[str] = []
        for path in (self._log_directory() / "Error.log", self._log_directory() / "RainbowDebugLog.log"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            candidates.extend(match.group(1).upper() for match in pattern.finditer(text))
        self.detected_device = candidates[-1] if candidates else ""
        return self.detected_device

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

    def _wait_for_listener(self, timeout: float = 30.0) -> None:
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

    def start(self, host: str, target_type: str, auth: str, scope_port: int = 4242, interface_type: str = "TCP/IP") -> None:
        host = host.strip()
        if not host:
            raise ValueError("TCP/IP host boş.")
        try:
            scope_port = int(scope_port)
        except (TypeError, ValueError) as exc:
            raise ValueError("SCOPE portu geçersiz.") from exc
        if not 1 <= scope_port <= 65535:
            raise ValueError("SCOPE portu 1-65535 arasında olmalı.")

        interface_type = interface_type.strip().upper()
        if interface_type not in {"TCP/IP", "USB"}:
            raise ValueError("Desteklenmeyen tünel arayüzü.")

        self.stop()
        self.last_diagnostics = ""

        exe = self._tunnel_exe()
        communication_dir = exe.parent
        if not self._is_com_handler_registered():
            raise RuntimeError(
                "Siemens SCOPE kurulu görünüyor ancak Rainbow COM bileşeni kayıtlı değil. "
                "SCOPE kurulumunu yönetici olarak Onar (Repair) seçeneğiyle tamamlayıp "
                "bilgisayarı yeniden başlatın."
            )
        interface_parameters = f"{host},{auth}"

        args = [
            str(exe),
            "--Port", str(self.local_port),
            "--RemotePort", str(self.remote_port),
            "--TargetType", target_type,
            "--InterfaceType", interface_type,
            "--InterfaceParameters", interface_parameters,
            "--IpAddress", self.local_host,
            "--TimeoutSeconds", "5",
            "--ReconnectTimeoutSeconds", "30",
            "--ReconnectDelaySeconds", "1",
            "--Verbose",
            "--LogData",
            "--LogHeaders",
        ]

        # RainbowTcpTunnel reads Console.ReadKey() while it is running.  A
        # windowed PyInstaller process has no console, and CREATE_NO_WINDOW
        # makes the Siemens process exit immediately after opening the port.
        # Give it a hidden console instead; the user still sees no console
        # window, but the tunnel remains alive like it does from CMD.
        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
        try:
            self._process = subprocess.Popen(
                args,
                cwd=str(communication_dir),
                stdin=None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
                startupinfo=startupinfo,
            )
        except OSError as exc:
            self._process = None
            raise RuntimeError(f"RainbowTcpTunnel başlatılamadı: {exc}") from exc

        self._target_host = host
        self.last_diagnostics = f"RainbowTcpTunnel: {exe}"

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
            # Do not probe the SCOPE port with a raw socket here.
            # Port 4242 is the proprietary Siemens SCOPE protocol; the
            # RainbowTcpTunnel process must own that connection itself.
            self._wait_for_listener()
            if interface_type == "USB":
                self._detect_usb_device()
        except Exception as exc:
            diagnostics = self._read_diagnostics()
            if diagnostics:
                self.last_diagnostics = diagnostics
            self.stop()
            detail = str(exc)
            if self.last_diagnostics and self.last_diagnostics not in detail:
                detail += f"\n{self.last_diagnostics}"
            raise RuntimeError(detail) from exc
