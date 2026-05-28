"""
conftest.py for CoAP tests.

Fixes event loop scoping between module-scoped aiocoap fixtures and
individual test functions on Python 3.12+ / pytest-asyncio 0.21.x.

Also ensures port 5683 is free before tests start (cross-platform).
"""
import asyncio
import socket
import subprocess
import sys
import time

import pytest


# ── Port cleanup ──────────────────────────────────────────────────────────────

def _port_in_use(port: int) -> bool:
    """Return True if something is bound to port on localhost (IPv4 or IPv6)."""
    for family, addr in [(socket.AF_INET6, "::1"), (socket.AF_INET, "127.0.0.1")]:
        try:
            s = socket.socket(family, socket.SOCK_DGRAM)
            s.bind((addr, port))
            s.close()
        except OSError:
            return True
    return False


def _free_port(port: int) -> None:
    """Kill whatever process holds port, then wait for it to release."""
    if not _port_in_use(port):
        return

    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                ["netstat", "-ano"], text=True, stderr=subprocess.DEVNULL
            )
            seen = set()
            for line in out.splitlines():
                if f":{port}" in line:
                    parts = line.split()
                    pid = parts[-1]
                    if pid.isdigit() and pid not in seen:
                        seen.add(pid)
                        subprocess.run(
                            ["taskkill", "/PID", pid, "/F"],
                            capture_output=True,
                        )
        except Exception:
            pass
    else:
        # Linux / Docker — try fuser, fall back to ss + kill
        freed = False
        for proto in ("tcp", "udp"):
            r = subprocess.run(
                ["fuser", "-k", f"{port}/{proto}"], capture_output=True
            )
            if r.returncode == 0:
                freed = True
        if not freed:
            try:
                out = subprocess.check_output(
                    ["ss", "-lpn", f"sport = :{port}"],
                    text=True, stderr=subprocess.DEVNULL,
                )
                for line in out.splitlines():
                    if "pid=" in line:
                        pid = line.split("pid=")[1].split(",")[0]
                        if pid.isdigit():
                            subprocess.run(["kill", "-9", pid], capture_output=True)
            except Exception:
                pass

    # Give the OS time to release the socket
    for _ in range(10):
        time.sleep(0.2)
        if not _port_in_use(port):
            break


@pytest.fixture(scope="session", autouse=True)
def ensure_coap_port_free():
    """Free port 5683 once per test session before the CoAP server starts."""
    _free_port(5683)
    yield


# ── Event-loop pinning ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _pin_module_event_loop(request):
    """
    Before every CoAP test function, set the module-scoped event_loop as the
    current (thread-local) event loop.  This prevents aiocoap from picking up
    a stale or wrong loop when it calls asyncio.get_event_loop() internally.
    """
    loop = request.getfixturevalue("event_loop")
    asyncio.set_event_loop(loop)
    yield
    # Leave the loop set — the module fixture will clean up on teardown.
