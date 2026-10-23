"""Tests for hci.dashboard: the light app, its token rule, and the always-on service files and commands."""

import plistlib
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi.testclient import TestClient

from hci import dashboard, metrics
from hci.config import get_settings
from hci.constants import DASHBOARD_LABEL, DASHBOARD_LOG, ROOT_DIR
from hci.types import ToolEvent

SCRIPT = Path("/repo/.venv/bin/hci-dashboard")


@pytest.mark.parametrize(
    ("host", "loopback"),
    [("127.0.0.1", True), ("::1", True), ("localhost", True), ("0.0.0.0", False), ("10.0.0.2", False)],
)
def test_is_loopback(host, loopback):
    """Only loopback addresses count as local."""
    # Act / Assert
    assert dashboard.is_loopback(host) is loopback


class TestApp:
    def test_loopback_needs_no_token(self):
        """On 127.0.0.1 the page and its data open without a token."""
        # Arrange
        metrics.emit(ToolEvent(tool="list_scenarios"))
        client = TestClient(dashboard.build_app("127.0.0.1"))
        # Act
        events = client.get("/api/metrics").json()
        # Assert
        assert [e["tool"] for e in events] == ["list_scenarios"]
        assert client.get("/dashboard").status_code == 200
        assert client.get("/vendor/chart.umd.min.js").status_code == 200

    def test_lan_host_needs_the_token(self, monkeypatch):
        """Bound to a LAN address, `/api/metrics` needs the API token."""
        # Arrange
        monkeypatch.setenv("HCI_TOKEN", "t")
        get_settings.cache_clear()
        client = TestClient(dashboard.build_app("0.0.0.0"))
        # Act / Assert
        assert client.get("/api/metrics").status_code == 401
        assert client.get("/api/metrics", headers={"Authorization": "Bearer t"}).status_code == 200

    def test_app_does_not_import_models(self):
        """The dashboard module pulls in no model, embedder or RAG code, so it starts fast."""
        # Arrange
        code = "import sys, hci.dashboard; print(any(m in sys.modules for m in ('torch', 'hci.rag', 'hci.index')))"
        # Act
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
        # Assert
        assert out.strip() == "False"


def test_launch_agent_plist_snapshot():
    """The LaunchAgent runs the venv's `hci-dashboard` from the repo, at login, kept alive, logging to logs/."""
    # Act
    plist = plistlib.loads(dashboard.launch_agent_plist(SCRIPT))
    # Assert
    assert plist == {
        "Label": DASHBOARD_LABEL,
        "ProgramArguments": [str(SCRIPT)],
        "WorkingDirectory": str(ROOT_DIR),
        "EnvironmentVariables": {
            "HCI_DASHBOARD_HOST": "127.0.0.1",
            "HCI_DASHBOARD_PORT": "8790",
            "HCI_METRICS_FILE": str(get_settings().metrics_file),
        },
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(DASHBOARD_LOG),
        "StandardErrorPath": str(DASHBOARD_LOG),
    }


def test_systemd_unit_runs_the_same_program():
    """The Linux unit restarts `hci-dashboard` from the repo and logs to the same file."""
    # Act
    unit = dashboard.systemd_unit(SCRIPT)
    # Assert
    assert f"ExecStart={SCRIPT}\n" in unit and f"WorkingDirectory={ROOT_DIR}\n" in unit
    assert "Restart=always" in unit and "WantedBy=default.target" in unit


class TestService:
    @pytest.fixture
    def launchctl(self, tmp_path, monkeypatch) -> Iterator[MagicMock]:
        """macOS with a temporary LaunchAgents folder and a mocked `launchctl`."""
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(dashboard, "LAUNCH_AGENTS_DIR", tmp_path / "LaunchAgents")
        monkeypatch.setattr(dashboard, "DASHBOARD_LOG", tmp_path / "logs" / "dashboard.log")
        monkeypatch.setattr(dashboard.os, "getuid", lambda: 501)
        with patch("hci.dashboard.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")) as run:
            yield run

    def test_install_writes_plist_and_bootstraps(self, launchctl, tmp_path):
        """Install boots out any old copy, writes the plist, then bootstraps it in the user's GUI domain."""
        # Act
        dashboard.install()
        # Assert
        path = tmp_path / "LaunchAgents" / f"{DASHBOARD_LABEL}.plist"
        assert plistlib.loads(path.read_bytes())["Label"] == DASHBOARD_LABEL
        assert [c.args[0] for c in launchctl.call_args_list] == [
            ["launchctl", "bootout", f"gui/501/{DASHBOARD_LABEL}"],
            ["launchctl", "bootstrap", "gui/501", str(path)],
        ]

    def test_uninstall_boots_out_and_removes(self, launchctl, tmp_path):
        """Uninstall unloads the agent and deletes its plist."""
        # Arrange
        dashboard.install()
        launchctl.reset_mock()
        # Act
        dashboard.uninstall()
        # Assert
        launchctl.assert_called_once_with(
            ["launchctl", "bootout", f"gui/501/{DASHBOARD_LABEL}"], capture_output=True, text=True, check=False
        )
        assert not (tmp_path / "LaunchAgents" / f"{DASHBOARD_LABEL}.plist").exists()

    @pytest.mark.parametrize(
        ("returncode", "stdout", "said"),
        [(0, "state = running", "Running"), (0, "state = waiting", "Loaded, not running"), (113, "", "Not running")],
    )
    def test_status_reads_launchctl_print(self, launchctl, capsys, returncode, stdout, said):
        """Status asks `launchctl print` and says whether the agent runs."""
        # Arrange
        launchctl.return_value = MagicMock(returncode=returncode, stdout=stdout, stderr="")
        # Act
        dashboard.status()
        # Assert
        assert launchctl.call_args == call(
            ["launchctl", "print", f"gui/501/{DASHBOARD_LABEL}"], capture_output=True, text=True, check=False
        )
        assert capsys.readouterr().out.startswith(said)

    def test_linux_prints_a_systemd_unit(self, monkeypatch, capsys):
        """Off macOS, install prints a systemd user unit and installs nothing."""
        # Arrange
        monkeypatch.setattr(sys, "platform", "linux")
        # Act
        with patch("hci.dashboard.subprocess.run") as run:
            dashboard.install()
        # Assert
        run.assert_not_called()
        assert "[Service]" in capsys.readouterr().out
