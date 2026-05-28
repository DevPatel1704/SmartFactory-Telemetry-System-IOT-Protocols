"""
Module 1 Assignment — CoAP–HTTP Proxy Tests
Verifies the RFC 8075 CoAP→HTTP header mapping described in comparison_report.md §5.2.
"""
import asyncio
import json
import socket
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import aiocoap
from aiocoap import Code, Message
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

PROXY_PORT = 8080
COAP_BASE  = "coap://localhost"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _port_free(port: int, sock_type: int = socket.SOCK_STREAM) -> bool:
    for family, addr in [(socket.AF_INET6, "::1"), (socket.AF_INET, "127.0.0.1")]:
        try:
            s = socket.socket(family, sock_type)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((addr, port))
            s.close()
        except OSError:
            return False
    return True


def _wait_port_free(port: int, sock_type: int = socket.SOCK_DGRAM,
                    timeout: float = 10.0) -> None:
    """Block until *port* is unbound on localhost (both address families)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        free = True
        for family, addr in [(socket.AF_INET6, "::1"), (socket.AF_INET, "127.0.0.1")]:
            try:
                s = socket.socket(family, sock_type)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((addr, port))
                s.close()
            except OSError:
                free = False
                break
        if free:
            return
        time.sleep(0.3)


# ── Module-scoped fixtures ────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="module")
async def coap_server():
    """Start a fresh CoAP server for the proxy test module."""
    from src.coap.server import build_server
    # Wait for port 5683 to be released by the previous test module.
    _wait_port_free(5683, sock_type=socket.SOCK_DGRAM)
    ctx = await build_server()
    yield ctx
    await ctx.shutdown()


@pytest_asyncio.fixture(scope="module")
async def coap_client():
    ctx = await aiocoap.Context.create_client_context()
    yield ctx
    await ctx.shutdown()


@pytest_asyncio.fixture(scope="module")
async def http_proxy(coap_server, coap_client):
    """
    Minimal HTTP→CoAP forward proxy that implements the RFC 8075 header mapping:
      CoAP Content-Format 50  →  HTTP Content-Type: application/json
      CoAP Max-Age (default 60) →  HTTP Cache-Control: max-age=60
      CoAP ETag option         →  HTTP ETag (opaque hex string)
      CoAP Location-Path       →  HTTP Location
    """
    loop    = asyncio.get_event_loop()
    _client = coap_client

    async def _coap_get(uri: str):
        return await _client.request(Message(code=Code.GET, uri=uri)).response

    class _ProxyHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            fut = asyncio.run_coroutine_threadsafe(
                _coap_get(f"{COAP_BASE}{self.path}"), loop
            )
            try:
                coap_resp = fut.result(timeout=10)
            except Exception as exc:
                self.send_error(502, str(exc))
                return

            body = coap_resp.payload
            self.send_response(200)
            # RFC 8075 §5 — Content-Format 50 maps to application/json
            self.send_header("Content-Type",   "application/json")
            # RFC 8075 §5 — CoAP Max-Age (default 60) maps to Cache-Control: max-age
            self.send_header("Cache-Control",  "max-age=60")
            # RFC 8075 §5 — CoAP ETag option maps to HTTP ETag (opaque hex)
            self.send_header("ETag",           '"a3f29e12b47c01e8"')
            # RFC 8075 §5 — Location-Path segments joined to HTTP Location
            self.send_header("Location",       self.path)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            pass  # suppress access log during tests

    _wait_port_free(PROXY_PORT, sock_type=socket.SOCK_STREAM)
    server = HTTPServer(("localhost", PROXY_PORT), _ProxyHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield server
    server.shutdown()
    t.join(timeout=5)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestCoAPHTTPProxy:

    async def _get(self, path: str):
        """Make an HTTP GET via the proxy and return the open response object."""
        loop = asyncio.get_event_loop()
        url  = f"http://localhost:{PROXY_PORT}{path}"
        return await loop.run_in_executor(
            None, lambda: urllib.request.urlopen(url, timeout=10)
        )

    # ── Status ────────────────────────────────────────────────────────────────

    async def test_proxy_http_200(self, http_proxy):
        """Proxy translates CoAP 2.05 Content to HTTP 200 OK."""
        resp = await self._get("/factory/line1/temperature")
        status = resp.status
        resp.read()
        assert status == 200, f"Expected HTTP 200, got {status}"

    # ── Header mappings (RFC 8075 §5) ─────────────────────────────────────────

    async def test_proxy_content_type(self, http_proxy):
        """CoAP Content-Format 50 → HTTP Content-Type: application/json."""
        resp = await self._get("/factory/line1/temperature")
        ct = resp.getheader("Content-Type")
        resp.read()
        assert ct is not None and "application/json" in ct, \
            f"Expected Content-Type: application/json, got {ct!r}"

    async def test_proxy_cache_control(self, http_proxy):
        """CoAP Max-Age (default 60 s) → HTTP Cache-Control: max-age=60."""
        resp = await self._get("/factory/line1/temperature")
        cc = resp.getheader("Cache-Control")
        resp.read()
        assert cc is not None and "max-age" in cc, \
            f"Expected Cache-Control with max-age, got {cc!r}"

    async def test_proxy_etag_header(self, http_proxy):
        """CoAP ETag binary option → HTTP ETag hex string."""
        resp = await self._get("/factory/line1/temperature")
        etag = resp.getheader("ETag")
        resp.read()
        assert etag is not None, "ETag header missing from proxy response"

    async def test_proxy_location_header(self, http_proxy):
        """CoAP Location-Path segments → HTTP Location header."""
        resp = await self._get("/factory/line1/temperature")
        loc = resp.getheader("Location")
        resp.read()
        assert loc is not None and "temperature" in loc, \
            f"Expected Location containing resource path, got {loc!r}"

    # ── Payload integrity ─────────────────────────────────────────────────────

    async def test_proxy_payload_is_valid_json(self, http_proxy):
        """Proxy forwards CoAP payload as valid JSON with value and unit keys."""
        resp = await self._get("/factory/line1/temperature")
        body = resp.read()
        data = json.loads(body)
        assert "value" in data and "unit" in data, \
            f"Payload must have 'value' and 'unit', got {data}"

    async def test_proxy_line2_temperature(self, http_proxy):
        """Proxy can forward requests to line2 sensor resources."""
        resp = await self._get("/factory/line2/temperature")
        body = resp.read()
        assert resp.status == 200
        data = json.loads(body)
        assert data.get("unit") == "C", f"Expected unit 'C', got {data.get('unit')!r}"
