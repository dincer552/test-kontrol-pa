from pathlib import Path

from tcp_tunnel import TcpTunnelManager


REQUIRED_FILES = (
    "RainbowTcpTunnel.exe",
    "RainbowTcpTunnelSrv.dll",
    "CommandLine.dll",
    "log4net.dll",
    "Interop.RAINBOWCOMHANDLERLib.dll",
)


def _write_communication_folder(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_FILES:
        (folder / name).write_bytes(b"test-runtime")


def test_installed_scope_tunnel_is_preferred(tmp_path, monkeypatch):
    scope_dir = tmp_path / "Program Files" / "Siemens" / "SCOPE" / "Communication"
    _write_communication_folder(scope_dir)
    manager = TcpTunnelManager()
    monkeypatch.setattr(manager, "_find_installed_tunnel", lambda: scope_dir / "RainbowTcpTunnel.exe")
    assert manager._tunnel_exe() == scope_dir / "RainbowTcpTunnel.exe"


def test_scope_installation_can_be_found_under_registry_install_root(tmp_path, monkeypatch):
    scope_root = tmp_path / "custom-drive" / "Siemens" / "SCOPE"
    communication = scope_root / "Communication"
    _write_communication_folder(communication)
    monkeypatch.setattr(TcpTunnelManager, "_registry_install_roots", staticmethod(lambda: [scope_root]))
    monkeypatch.setattr(TcpTunnelManager, "_scope_search_roots", staticmethod(lambda: [scope_root]))
    manager = TcpTunnelManager()
    found = manager._find_installed_tunnel()
    assert found == communication / "RainbowTcpTunnel.exe"


def test_no_scope_installation_returns_clear_error(monkeypatch):
    monkeypatch.setattr(TcpTunnelManager, "_scope_search_roots", staticmethod(lambda: []))
    monkeypatch.setattr("tcp_tunnel.shutil.which", lambda _name: None)
    manager = TcpTunnelManager()
    try:
        manager._tunnel_exe()
    except FileNotFoundError as exc:
        assert "SCOPE/Communication kurulumu bulunamadı" in str(exc)
        assert "Communication.zip indirmez" in str(exc)
    else:
        raise AssertionError("Missing SCOPE installation should be reported")


def test_incomplete_scope_communication_folder_is_rejected(tmp_path):
    folder = tmp_path / "Communication"
    folder.mkdir()
    (folder / "RainbowTcpTunnel.exe").write_bytes(b"exe")
    assert not TcpTunnelManager._has_tunnel_files(folder)
