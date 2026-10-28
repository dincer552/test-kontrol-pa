import json
from types import SimpleNamespace

import pytest

import connection
from connection import C600ConnectionMixin


class _Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'[{"value":"123"}]'


def _reader(mode, host, port, tunnel_running):
    reader = object.__new__(C600ConnectionMixin)
    reader._c600_connection_var = _Value(mode)
    reader._c600_host_var = _Value(host)
    reader._c600_port_var = _Value(port)
    reader._c600_tcp_tunnel = SimpleNamespace(
        running=tunnel_running,
        local_host="127.0.0.1",
        local_port=4243,
    )
    return reader


def test_usb_json_read_uses_local_tunnel_not_detected_device_name(monkeypatch):
    requested = []
    monkeypatch.setattr(
        connection.urllib.request,
        "urlopen",
        lambda request, timeout: (requested.append(request.full_url) or _Response()),
    )
    reader = _reader("USB Direct Tunnel", "POL648_CAE72C", "4243", True)

    result = reader._c600_json_read("AIR_FLOW")

    assert result["value"] == "123"
    assert requested[0].startswith("http://127.0.0.1:4243/json.html?")
    assert "POL648_CAE72C" not in requested[0]


def test_usb_json_read_reports_stopped_tunnel_instead_of_dns_error(monkeypatch):
    def unexpected_urlopen(*_args, **_kwargs):
        pytest.fail("HTTP must not be attempted when the USB tunnel is stopped")

    monkeypatch.setattr(connection.urllib.request, "urlopen", unexpected_urlopen)
    reader = _reader("USB Direct Tunnel", "POL648_CAE72C", "4243", False)

    with pytest.raises(ConnectionError, match="USB Direct"):
        reader._c600_json_read("AIR_FLOW")
