"""
Module 1 Assignment — Task 2.1
CoAP Sensor Resource Server

Complete all TODO sections. The resource classes must match the
URIs and behaviours listed in the assignment spec.

Run with:  python -m src.coap.server
"""

import asyncio
import json
import logging
import random
from datetime import datetime, timezone

import aiocoap
import aiocoap.resource as resource
from aiocoap import Code, Message

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger(__name__)

# ── Sensor simulation helpers ─────────────────────────────────────────────────

SENSOR_CONFIG = {
    "temperature": {"unit": "C",    "base": 70.0, "noise": 3.0},
    "vibration":   {"unit": "mm/s", "base": 1.2,  "noise": 0.3},
    "power":       {"unit": "kW",   "base": 45.0, "noise": 5.0},
}

def _sim(sensor: str) -> dict:
    cfg = SENSOR_CONFIG[sensor]
    return {
        "value": round(cfg["base"] + random.gauss(0, cfg["noise"]), 3),
        "unit":  cfg["unit"],
        "ts":    datetime.now(timezone.utc).isoformat(),
    }

def _json(data: dict) -> bytes:
    return json.dumps(data).encode()


# ── Observable Sensor Resource ────────────────────────────────────────────────

class SensorResource(resource.ObservableResource):
    """
    An observable CoAP resource that represents a single sensor on a line.
    Updates every 5 seconds and notifies all registered observers.
    """

    def __init__(self, line: str, sensor_type: str):
        super().__init__()
        self.line        = line
        self.sensor_type = sensor_type
        self._reading    = _sim(sensor_type)
        self._task       = asyncio.ensure_future(self._update_loop())

    async def _update_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(5)
                self._reading = _sim(self.sensor_type)
                log.info(
                    f"[{self.line}/{self.sensor_type}] updated: "
                    f"{self._reading['value']} {self._reading['unit']}"
                )
                self.updated_state()
        except asyncio.CancelledError:
            pass

    async def render_get(self, request: Message) -> Message:
        payload = _json(self._reading)
        return Message(code=Code.CONTENT, payload=payload, content_format=50)


# ── Actuator Resource ─────────────────────────────────────────────────────────

class ActuatorResource(resource.Resource):
    """
    A CoAP resource representing a controllable fan actuator.
    Accepts PUT with {"state": "ON"} or {"state": "OFF"}.
    """

    def __init__(self):
        super().__init__()
        self._state = "OFF"

    async def render_get(self, request: Message) -> Message:
        payload = _json({"state": self._state})
        return Message(code=Code.CONTENT, payload=payload, content_format=50)

    async def render_put(self, request: Message) -> Message:
        try:
            data = json.loads(request.payload.decode())
            state = data.get("state")
            if state not in ("ON", "OFF"):
                return Message(
                    code=Code.BAD_REQUEST,
                    payload=b"state must be ON or OFF",
                )
            self._state = state
            log.info(f"Fan actuator set to {state}")
            return Message(
                code=Code.CHANGED,
                payload=_json({"state": self._state}),
                content_format=50,
            )
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Message(code=Code.BAD_REQUEST, payload=b"invalid JSON payload")


# ── Block-wise Manifest Resource ──────────────────────────────────────────────

class ManifestResource(resource.Resource):
    """
    A large resource that triggers CoAP Block2 transfer.
    Returns a JSON firmware manifest >= 3072 bytes.
    aiocoap handles Block2 fragmentation automatically.
    """

    async def render_get(self, request: Message) -> Message:
        sensor_types = ["temperature", "vibration", "power", "pressure", "humidity", "co2"]
        lines = ["line1", "line2"]
        entries = []
        for i in range(60):
            sensor = sensor_types[i % len(sensor_types)]
            line   = lines[i % len(lines)]
            entry = {
                "id":               f"fw-{line}-{sensor}-{i:03d}",
                "sensor_type":      sensor,
                "production_line":  line,
                "firmware_version": f"2.{i // 10}.{i % 10}",
                "checksum_sha256":  (f"a{i:02x}b{i:02x}c{i:02x}d{i:02x}") * 4,
                "update_url": (
                    f"coap://firmware.smartfactory.local"
                    f"/sensors/{sensor}/v2.{i // 10}.{i % 10}.bin"
                ),
                "size_bytes":   32768 + i * 512,
                "release_date": f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}T00:00:00Z",
                "release_notes": (
                    f"Firmware update for {sensor} sensor on {line}. "
                    f"Improved accuracy and reduced power consumption. "
                    f"Bug fixes for edge cases in data reporting pipeline. "
                    f"Enhanced self-diagnostics and watchdog timer support."
                ),
                "required_hardware": f"SmartSensor-{sensor[:4].upper()}-v3",
                "min_hw_version":    "3.0",
                "dependencies":      [f"base-fw-{i % 3}", f"sensor-lib-{sensor}"],
                "signature":         f"RSA-SHA256:{i:08x}" + "0" * 32,
            }
            entries.append(entry)

        manifest = {
            "manifest_version": "2.0",
            "generated_at":     "2024-01-15T12:00:00Z",
            "factory":          "SmartFactory-Plant-A",
            "total_devices":    len(entries),
            "firmware_entries": entries,
        }
        payload = _json(manifest)
        log.info(f"Manifest size: {len(payload)} bytes")
        assert len(payload) >= 3072, f"Manifest too small: {len(payload)} bytes"
        return Message(code=Code.CONTENT, payload=payload, content_format=50)


# ── Resource Tree & Server Setup ──────────────────────────────────────────────

class _ServerContext:
    """Thin wrapper around aiocoap.Context that also cancels sensor update tasks."""

    def __init__(self, ctx: aiocoap.Context, sensor_tasks: list):
        self._ctx          = ctx
        self._sensor_tasks = sensor_tasks

    async def shutdown(self) -> None:
        for task in self._sensor_tasks:
            task.cancel()
        await asyncio.gather(*self._sensor_tasks, return_exceptions=True)
        await self._ctx.shutdown()

    def __getattr__(self, name: str):
        return getattr(self._ctx, name)


async def build_server() -> "_ServerContext":
    """Build the CoAP resource tree and create the server context."""
    import socket
    # Resolve 'localhost' the same way the aiocoap client will, so server and
    # client always use the same address family (IPv4 or IPv6 depending on OS).
    _info = socket.getaddrinfo("localhost", 5683, type=socket.SOCK_DGRAM)
    _bind_host = _info[0][4][0]
    log.info(f"CoAP server will bind to {_bind_host}:5683")

    root = resource.Site()

    # Sensor resources — line1
    sensors = [
        SensorResource("line1", "temperature"),
        SensorResource("line1", "vibration"),
        SensorResource("line1", "power"),
        SensorResource("line2", "temperature"),
    ]
    root.add_resource(["factory", "line1", "temperature"], sensors[0])
    root.add_resource(["factory", "line1", "vibration"],   sensors[1])
    root.add_resource(["factory", "line1", "power"],       sensors[2])
    root.add_resource(["factory", "line2", "temperature"], sensors[3])

    # Actuator
    root.add_resource(["actuator", "line1", "fan"], ActuatorResource())

    # Firmware manifest (Block2)
    root.add_resource(["factory", "manifest"], ManifestResource())

    # Service discovery
    root.add_resource(
        [".well-known", "core"],
        resource.WKCResource(root.get_resources_as_linkheader),
    )

    context = await aiocoap.Context.create_server_context(root, bind=(_bind_host, 5683))
    return _ServerContext(context, [s._task for s in sensors])


async def main() -> None:
    context = await build_server()
    log.info("CoAP server running on coap://localhost:5683")
    log.info(
        "Resources: /factory/line{1,2}/{temperature,vibration,power}"
        ", /actuator/line1/fan, /factory/manifest"
    )
    await asyncio.get_event_loop().create_future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
