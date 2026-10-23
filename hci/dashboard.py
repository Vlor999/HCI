"""Metrics dashboard: the page, `GET /api/metrics` and the vendored libraries, over the metrics JSONL file.

Imports no model, embedder or RAG, so `hci-dashboard` starts fast, costs little memory and can run all the time
(`hci dashboard --install`). `hci serve` adds the same routes behind its token.
"""

import ipaddress
import os
import plistlib
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from hci import metrics
from hci.auth import auth
from hci.config import get_settings
from hci.constants import (
    DASHBOARD_LABEL,
    DASHBOARD_LOG,
    DASHBOARD_PAGE,
    DASHBOARD_SCRIPT,
    LAUNCH_AGENTS_DIR,
    METRICS_DEFAULT_LIMIT,
    METRICS_MAX_LIMIT,
    ROOT_DIR,
    SERVER_START_WAIT_S,
    SYSTEMD_HELP,
    SYSTEMD_UNIT,
    SYSTEMD_UNIT_NAME,
    VENDOR_DIR,
)


def dashboard_page() -> FileResponse:
    """Serve the dashboard page; it reads its data from `/api/metrics`.

    Returns:
        The page.
    """
    return FileResponse(DASHBOARD_PAGE)


def get_metrics(
    since: float | None = Query(default=None, description="Only events after this epoch timestamp, in seconds."),
    limit: int = Query(default=METRICS_DEFAULT_LIMIT, ge=1, le=METRICS_MAX_LIMIT, description="Last N events."),
) -> list[dict]:
    """Metric events from the metrics file, oldest first.

    Args:
        since: Only events with a later timestamp.
        limit: Only the last `limit` events.

    Returns:
        The events, as written (see `hci.metrics.record`).
    """
    return metrics.read(since, limit)


def add_routes(app: FastAPI, require_token: bool) -> None:
    """Add `/dashboard` (open, like `/`) and `/api/metrics` (token-checked when asked) to an app.

    Args:
        app: The app.
        require_token: Check the bearer token on `/api/metrics`.
    """
    app.add_api_route("/dashboard", dashboard_page, methods=["GET"])
    app.add_api_route(
        "/api/metrics", get_metrics, methods=["GET"], dependencies=[Depends(auth)] if require_token else []
    )


def is_loopback(host: str) -> bool:
    """Whether a bind address is reachable from this machine only.

    Args:
        host: The bind address.

    Returns:
        True for `localhost` and loopback IPs.
    """
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def build_app(host: str) -> FastAPI:
    """The dashboard app; the token is required unless it binds to loopback.

    Args:
        host: The bind address.

    Returns:
        The app.
    """
    app = FastAPI(title="HCI metrics dashboard")
    app.mount("/vendor", StaticFiles(directory=VENDOR_DIR), name="vendor")
    add_routes(app, require_token=not is_loopback(host))
    return app


def _open_when_listening(host: str, port: int, url: str) -> None:
    """Open `url` in the browser once something listens on `host:port`, or after `SERVER_START_WAIT_S`."""
    deadline = time.monotonic() + SERVER_START_WAIT_S
    while time.monotonic() < deadline:
        try:
            socket.create_connection((host, port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    webbrowser.open(url)


def run(host: str, port: int, open_browser: bool = False) -> None:
    """Serve the dashboard and print its URL (with the token when the host is not loopback).

    Args:
        host: Bind address.
        port: Port.
        open_browser: Open the URL in this machine's browser once the server listens.
    """
    local = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{local}:{port}/dashboard" + ("" if is_loopback(host) else f"#{get_settings().token}")
    print(f"Metrics dashboard: {url}")
    if open_browser:
        threading.Thread(target=_open_when_listening, args=(local, port, url), daemon=True).start()
    uvicorn.run(build_app(host), host=host, port=port)


def main() -> None:
    """`hci-dashboard`: serve the dashboard on the configured host and port (what the always-on service runs)."""
    settings = get_settings()
    run(settings.dashboard_host, settings.dashboard_port)


# --- always-on service ---------------------------------------------------------


def program() -> Path:
    """The `hci-dashboard` script of the running venv, by absolute path.

    Returns:
        Its path, next to the Python running this.
    """
    return Path(sys.executable).with_name(DASHBOARD_SCRIPT)


def launch_agent_path() -> Path:
    """Where the macOS LaunchAgent plist goes.

    Returns:
        `~/Library/LaunchAgents/<label>.plist`.
    """
    return LAUNCH_AGENTS_DIR / f"{DASHBOARD_LABEL}.plist"


def launch_agent_plist(script: Path) -> bytes:
    """The LaunchAgent that keeps the dashboard running from login, with the current dashboard settings.

    Args:
        script: Absolute path to `hci-dashboard`.

    Returns:
        The plist XML.
    """
    settings = get_settings()
    environment = {
        "HCI_DASHBOARD_HOST": settings.dashboard_host,
        "HCI_DASHBOARD_PORT": str(settings.dashboard_port),
        "HCI_METRICS_FILE": str(settings.metrics_file),
    }
    return plistlib.dumps(
        {
            "Label": DASHBOARD_LABEL,
            "ProgramArguments": [str(script)],
            "WorkingDirectory": str(ROOT_DIR),
            "EnvironmentVariables": environment,
            "RunAtLoad": True,
            "KeepAlive": True,
            "StandardOutPath": str(DASHBOARD_LOG),
            "StandardErrorPath": str(DASHBOARD_LOG),
        }
    )


def systemd_unit(script: Path) -> str:
    """The systemd user unit equivalent to the LaunchAgent, for Linux.

    Args:
        script: Absolute path to `hci-dashboard`.

    Returns:
        The unit file text.
    """
    return SYSTEMD_UNIT.format(program=script, root=ROOT_DIR, log=DASHBOARD_LOG)


def _launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, check=False)


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _print_systemd() -> None:
    print(systemd_unit(program()))
    print(SYSTEMD_HELP.format(unit=SYSTEMD_UNIT_NAME))


def install() -> None:
    """Install and start the always-on dashboard: a LaunchAgent on macOS; elsewhere, print a systemd user unit."""
    if sys.platform != "darwin":
        return _print_systemd()
    _launchctl("bootout", f"{_domain()}/{DASHBOARD_LABEL}")  # reinstall cleanly; fails harmlessly if not loaded
    DASHBOARD_LOG.parent.mkdir(parents=True, exist_ok=True)
    path = launch_agent_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(launch_agent_plist(program()))
    result = _launchctl("bootstrap", _domain(), str(path))
    port = get_settings().dashboard_port
    print(f"Installed {path}" if result.returncode == 0 else f"launchctl bootstrap failed: {result.stderr.strip()}")
    print(f"Dashboard: http://127.0.0.1:{port}/dashboard (log: {DASHBOARD_LOG})")


def uninstall() -> None:
    """Stop the always-on dashboard and remove its LaunchAgent; elsewhere, print the systemd commands."""
    if sys.platform != "darwin":
        return _print_systemd()
    _launchctl("bootout", f"{_domain()}/{DASHBOARD_LABEL}")
    launch_agent_path().unlink(missing_ok=True)
    print(f"Removed {DASHBOARD_LABEL}")


def status() -> None:
    """Say whether the always-on dashboard is installed and running."""
    if sys.platform != "darwin":
        return _print_systemd()
    result = _launchctl("print", f"{_domain()}/{DASHBOARD_LABEL}")
    if result.returncode != 0:
        print("Not running" + (" (plist present, not loaded)" if launch_agent_path().exists() else ""))
    else:
        print("Running" if "state = running" in result.stdout else "Loaded, not running (see the log)")
