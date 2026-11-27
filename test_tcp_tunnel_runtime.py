from pathlib import Path
import zipfile

import pytest

from tcp_tunnel import TcpTunnelManager


REQUIRED_FILES = (
    "RainbowTcpTunnel.exe",
    "RainbowTcpTunnelSrv.dll",
    "CommandLine.dll",
    "log4net.dll",
    "Interop.RAINBOWCOMHANDLERLib.dll",
    "TcpTunnel.log4net.config",
)


def _write_communication_folder(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_FILES:
        (folder / name).write_bytes(b"test-runtime")


def _write_communication_zip(path: Path, *, extra=()) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in REQUIRED_FILES:
            archive.writestr(f"Communication/{name}", b"test-runtime")
        for name, payload in extra:
            archive.writestr(name, payload)


def test_communication_zip_extracts_to_local_runtime(tmp_path):
    archive = tmp_path / "Communication.zip"
    destination = tmp_path / "LocalAppData" / "TestKontrol" / "Communication"
    _write_communication_zip(archive)

    resolved = TcpTunnelManager._safe_extract_communication_zip(archive, destination)

    assert resolved == destination
    assert TcpTunnelManager._has_tunnel_files(resolved)
    assert (resolved / "RainbowTcpTunnel.exe").read_bytes() == b"test-runtime"


def test_communication_zip_rejects_path_traversal(tmp_path):
    archive = tmp_path / "Communication.zip"
    destination = tmp_path / "LocalAppData" / "TestKontrol" / "Communication"
    _write_communication_zip(
        archive,
        extra=(("Communication/../../escaped.txt", b"not allowed"),),
    )

    with pytest.raises(ValueError, match="Güvensiz Communication ZIP yolu"):
        TcpTunnelManager._safe_extract_communication_zip(archive, destination)

    assert not (tmp_path / "LocalAppData" / "TestKontrol" / "escaped.txt").exists()


def test_sidecar_communication_zip_is_discovered_automatically(tmp_path, monkeypatch):
    app_dir = tmp_path / "portable"
    archive = app_dir / "Communication.zip"
    runtime = tmp_path / "LocalAppData" / "TestKontrol" / "Communication"
    _write_communication_zip(archive)

    monkeypatch.setattr(TcpTunnelManager, "_resource_root", staticmethod(lambda: app_dir))
    monkeypatch.setattr(TcpTunnelManager, "_application_dir", staticmethod(lambda: app_dir))
    monkeypatch.setattr(TcpTunnelManager, "_runtime_dir", staticmethod(lambda: runtime))

    resolved = TcpTunnelManager()._communication_dir()

    assert resolved == runtime
    assert TcpTunnelManager._has_tunnel_files(resolved)


def test_bundled_communication_folder_is_copied_to_stable_location(tmp_path, monkeypatch):
    bundle_root = tmp_path / "pyinstaller"
    bundled = bundle_root / "Communication"
    runtime = tmp_path / "LocalAppData" / "TestKontrol" / "Communication"
    _write_communication_folder(bundled)

    monkeypatch.setattr(TcpTunnelManager, "_resource_root", staticmethod(lambda: bundle_root))
    monkeypatch.setattr(TcpTunnelManager, "_application_dir", staticmethod(lambda: tmp_path / "app"))
    monkeypatch.setattr(TcpTunnelManager, "_runtime_dir", staticmethod(lambda: runtime))

    resolved = TcpTunnelManager()._communication_dir()

    assert resolved == runtime
    assert TcpTunnelManager._has_tunnel_files(resolved)
    assert (resolved / "RainbowTcpTunnel.exe").read_bytes() == b"test-runtime"


def test_incomplete_communication_package_is_not_accepted(tmp_path):
    folder = tmp_path / "Communication"
    folder.mkdir()
    (folder / "RainbowTcpTunnel.exe").write_bytes(b"exe")

    assert not TcpTunnelManager._has_tunnel_files(folder)
