"""
Module 1 Assignment — Task 2.2
CoAP Observer Client

Complete all TODO sections.

Run with:  python -m src.coap.observer
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

import aiocoap
from aiocoap import Message, Code

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger(__name__)

SERVER_BASE      = "coap://localhost"
OBSERVE_DURATION = 60   # seconds before clean deregister
WRAP_THRESHOLD   = 2 ** 24  # CoAP Observe sequence number wrap-around point


class FactoryObserver:
    """Observes CoAP sensor resources and reassembles Block2 transfers."""

    def __init__(self):
        self._ctx = None
        self._last_seq: dict[str, int]   = {}   # uri -> last observe sequence number
        self._stale_count: dict[str, int] = {}  # uri -> stale notification count

    # ── Setup ──────────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Create the aiocoap client context."""
        self._ctx = await aiocoap.Context.create_client_context()

    async def stop(self) -> None:
        """Clean up the context."""
        if self._ctx:
            await self._ctx.shutdown()

    # ── Observation ────────────────────────────────────────────────────────────

    async def observe_resource(self, uri: str) -> None:
        """
        Subscribe to a single observable CoAP resource for OBSERVE_DURATION seconds,
        then deregister cleanly with Observe=1.
        """
        request = Message(code=Code.GET, uri=uri, observe=0)
        pr = self._ctx.request(request)

        try:
            async def _collect():
                async for response in pr.observation:
                    self._handle_notification(uri, response)

            await asyncio.wait_for(_collect(), timeout=OBSERVE_DURATION)
        except asyncio.TimeoutError:
            pass
        finally:
            pr.observation.cancel()
            log.info(f"Deregistered from {uri}")

    def _handle_notification(self, uri: str, response: Message) -> None:
        """Process a single Observe notification, detecting stale sequences."""
        seq = response.opt.observe

        # Stale detection with wrap-around support
        last = self._last_seq.get(uri, -1)
        if last >= 0:
            # A notification is stale if seq <= last, unless it has wrapped around
            is_wrap = last > (WRAP_THRESHOLD - 256) and seq < 256
            if seq <= last and not is_wrap:
                self._stale_count[uri] = self._stale_count.get(uri, 0) + 1
                log.warning(f"STALE notification on {uri}: seq={seq} <= last={last}")
                return

        self._last_seq[uri] = seq

        try:
            data  = json.loads(response.payload.decode())
            value = data.get("value", "?")
            unit  = data.get("unit", "")
            ts    = data.get("ts", datetime.now(timezone.utc).isoformat())
        except (json.JSONDecodeError, UnicodeDecodeError):
            value = response.payload
            unit  = ""
            ts    = datetime.now(timezone.utc).isoformat()

        log.info(f"[OBSERVE] {uri}  seq={seq}  val={value} {unit}  @ {ts}")

    # ── Block2 Transfer ────────────────────────────────────────────────────────

    async def fetch_manifest(self) -> None:
        """
        GET /factory/manifest — aiocoap automatically reassembles Block2 blocks.
        Logs total bytes received and number of firmware entries.
        """
        uri = f"{SERVER_BASE}/factory/manifest"
        request = Message(code=Code.GET, uri=uri)
        response = await self._ctx.request(request).response

        payload = response.payload
        log.info(f"Manifest received: {len(payload)} bytes")
        block_count = (len(payload) + 1023) // 1024
        log.info(f"Block2 blocks reassembled: ~{block_count}")

        try:
            data = json.loads(payload.decode())
            if isinstance(data, dict) and "firmware_entries" in data:
                count = len(data["firmware_entries"])
            elif isinstance(data, list):
                count = len(data)
            else:
                count = 0
            log.info(f"Firmware entries in manifest: {count}")
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            log.error(f"Failed to parse manifest JSON: {exc}")

        log.info("Block2 transfer complete")

    # ── Run ────────────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Run concurrent observations on both temperature resources, then fetch manifest."""
        await self.start()
        try:
            uris = [
                f"{SERVER_BASE}/factory/line1/temperature",
                f"{SERVER_BASE}/factory/line2/temperature",
            ]
            log.info(f"Starting {OBSERVE_DURATION}s observation on both temperature resources…")
            await asyncio.gather(*(self.observe_resource(uri) for uri in uris))

            await self.fetch_manifest()

            # Final summary
            log.info("── Observation Summary ──────────────────────────────")
            for uri in uris:
                stale = self._stale_count.get(uri, 0)
                log.info(f"  {uri}: stale notifications = {stale}")
            log.info("─────────────────────────────────────────────────────")
        finally:
            await self.stop()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    observer = FactoryObserver()
    asyncio.run(observer.run())
