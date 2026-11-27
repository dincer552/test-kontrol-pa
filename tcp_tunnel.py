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
    def _resource_root() -> Path:
        return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

    @staticmethod
    def _application_dir() -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parent

    @staticmethod
    def _runtime_dir() -> Path:
        local_app_data = os.environ.get("LOCALAPPDATA")
        root = Path(local_app_data) if local_app_data else Path.home() / ".test-kontrol"
        return root / "TestKontrol" / "Communication"

    @staticmethod
    def _has_tunnel_files(folder: Path) -> bool:
        required = (
            "RainbowTcpTunnel.exe",
            "RainbowTcpTunnelSrv.dll",
            "CommandLine.dll",
            "log4net.dll",
            "Interop.RAINBOWCOMHANDLERLib.dll",
            "TcpTunnel.log4net.config",
        )
        return folder.is_dir() and all((folder / name).is_file() for name in required)

    @staticmethod
    def _safe_extract_communication_zip(archive_path: Path, destination: Path) -> Path:
        """Extract the supplied Siemens Communication archive without allowing ZIP path traversal."""
        import hashlib
        import zipfile
        from pathlib import PurePosixPath

        digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        marker = destination.parent / f".communication-{digest}.ready"
        if marker.is_file() and TcpTunnelManager._has_tunnel_files(destination):
            return destination

        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(archive_path) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    raw_name = info.filename.replace("\\", "/")
                    member = PurePosixPath(raw_name)
                    if member.is_absolute() or ".." in member.parts:
                        raise ValueError(f"Güvensiz Communication ZIP yolu: {info.filename}")
                    parts = member.parts
                    if parts and parts[0].lower() == "communication":
                        parts = parts[1:]
                    if not parts:
                        continue
                    target = destination.joinpath(*parts)
                    resolved_target = target.resolve()
                    resolved_root = destination.resolve()
                    if resolved_root not in resolved_target.parents:
                        raise ValueError(f"ZIP hedef klasörünün dışına çıkıyor: {info.filename}")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise

        if not TcpTunnelManager._has_tunnel_files(destination):
            raise FileNotFoundError(
                "Communication.zip bulundu ancak RainbowTcpTunnel için gerekli dosyalar eksik."
            )
        marker.write_text(digest, encoding="ascii")
        return destination

    def _communication_dir(self) -> Path:
        resource_root = self._resource_root()
        app_dir = self._application_dir()
        runtime_dir = self._runtime_dir()

        # In a PyInstaller --onefile build, _MEIPASS is temporary. Copy the
        # communication runtime to LocalAppData so COM registration always
        # points to a stable path between application launches.
        bundled_folder = resource_root / "Communication"
        if self._has_tunnel_files(bundled_folder):
            if bundled_folder.resolve() == runtime_dir.resolve():
                return bundled_folder
            shutil.copytree(bundled_folder, runtime_dir, dirs_exist_ok=True)
            if self._has_tunnel_files(runtime_dir):
                return runtime_dir

        # A side-by-side folder is useful for portable development or ZIP builds.
        side_by_side = app_dir / "Communication"
        if self._has_tunnel_files(side_by_side):
            return side_by_side

        # Also accept the original Communication.zip next to the EXE, so users
        # can move the application and the vendor runtime to another PC without
        # installing the complete SCOPE application.
        zip_candidates = (
            app_dir / "Communication.zip",
            resource_root / "Communication.zip",
        )
        for archive_path in zip_candidates:
            if archive_path.is_file():
                return self._safe_extract_communication_zip(archive_path, runtime_dir)

        if self._has_tunnel_files(runtime_dir):
            return runtime_dir
        return runtime_dir

    @staticmethod
    def _is_com_handler_registered() -> bool:
        """Check the 32-bit Siemens Rainbow COM local-server registration."""
        if sys.platform != "win32":
            return True
        try:
            import winreg

            clsid = r"CLSID\\{B14C61DD-E5EB-4735-941E-03E400367B2E}\\LocalServer32"
            access = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_32KEY", 0)
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, clsid, 0, access) as key:
                server, _ = winreg.QueryValueEx(key, "")
            match = re.match(r'\\s*"([^"]+)"', str(server))
            server_path = match.group(1) if match else str(server).split(" ", 1)[0]
            return Path(os.path.expandvars(server_path)).is_file()
        except (OSError, ImportError, ValueError):
            return False

    def _ensure_com_handler_registered(self, communication_dir: Path) -> None:
        """Register the bundled COM helper on first use, without touching an existing SCOPE registration."""
        if sys.platform != "win32" or self._is_com_handler_registered():
            return

        handler_exe = communication_dir / "RainbowComHandler.exe"
        handler_dll = communication_dir / "RainbowComHandler.dll"
        proxy_dll = communication_dir / "RainbowComHandlerPS.dll"
        if not (handler_exe.is_file() and handler_dll.is_file() and proxy_dll.is_file()):
            raise RuntimeError(
                "Siemens Rainbow COM bileşeni kayıtlı değil ve Communication paketinde "
                "kayıt için gereken dosyalar bulunamadı."
            )

        script = communication_dir / "register_rainbow_com.cmd"
        script.write_text(
            "@echo off\\r\\n"
            "cd /d \\"%~dp0\\"\\r\\n"
            'set "REGSVR=%SystemRoot%\\\\SysWOW64\\\\regsvr32.exe"\\r\\n'
            'if not exist "%REGSVR%" set "REGSVR=%SystemRoot%\\\\System32\\\\regsvr32.exe"\\r\\n'
            '"%REGSVR%" /u /s "%~dp0RainbowComHandler.dll" > "%~dp0register_rainbow_com.log" 2>&1\\r\\n'
            '"%~dp0RainbowComHandler.exe" /RegServer >> "%~dp0register_rainbow_com.log" 2>&1\\r\\n'
            "if errorlevel 1 exit /b 1\\r\\n"
            '"%REGSVR%" /s "%~dp0RainbowComHandlerPS.dll" >> "%~dp0register_rainbow_com.log" 2>&1\\r\\n'
            "if errorlevel 1 exit /b 1\\r\\n"
            "exit /b 0\\r\\n",
            encoding="utf-8",
        )

        import ctypes
        command = os.path.join(os.environ.get("SystemRoot", r"C:\\Windows"), "System32", "cmd.exe")
        params = f'/c "{script}"'
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", command, params, str(communication_dir), 0
        )
        if result <= 32:
            raise RuntimeError(
                "Siemens Rainbow COM bileşeni için kayıt gerekiyor. Windows yönetici izni "
                "verilmediği için otomatik kurulum başlatılamadı."
            )

        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if self._is_com_handler_registered():
                return
            time.sleep(0.25)

        log_path = communication_dir / "register_rainbow_com.log"
        detail = ""
        try:
            if log_path.is_file():
                detail = log_path.read_text(encoding="utf-8", errors="replace")[-1200:]
        except OSError:
            pass
        raise RuntimeError(
            "Siemens Rainbow COM bileşeni kaydedilemedi. SCOPE kurmadan devam etmek için "
            "Communication paketinin Windows kayıt işlemi tamamlanmalı. "
            + detail
        )

    def _tunnel_exe(self) -> Path:
        bundled_dir = self._communication_dir()
        bundled = bundled_dir / "RainbowTcpTunnel.exe"
        if self._has_tunnel_files(bundled_dir):
            return bundled

        found = shutil.which("RainbowTcpTunnel.exe")
        if found:
            return Path(found)

        candidates: list[Path] = []
        roots = (
            Path(r"C:\\Program Files\\Siemens"),
            Path(r"C:\\Program Files (x86)\\Siemens"),
            Path(r"C:\\Program Files\\Common Files\\Rainbow"),
            Path(r"C:\\Program Files (x86)\\Common Files\\Rainbow"),
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
            if self._has_tunnel_files(path.parent)
        ]
        if valid:
            return max(valid, key=lambda path: path.stat().st_mtime)

        if candidates:
            return max(candidates, key=lambda path: path.stat().st_mtime)

        raise FileNotFoundError(
            "RainbowTcpTunnel çalışma paketi bulunamadı. EXE yanına Communication.zip "
            "koyun, Communication klasörünü ekleyin veya Siemens SCOPE/Communication kurun."
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
        self._ensure_com_handler_registered(communication_dir)
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
