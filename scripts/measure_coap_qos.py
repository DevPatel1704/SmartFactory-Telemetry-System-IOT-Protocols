"""
Measure CoAP NON vs CON latency and loss over 100 requests each.
Run with: python scripts/measure_coap_qos.py
"""
import asyncio
import time
from src.coap.server import build_server
import aiocoap
from aiocoap import Message, Code
from aiocoap.numbers.types import Type

URI = "coap://localhost/factory/line1/temperature"
N   = 100


async def measure(client, mtype, label):
    sent = received = dupes = 0
    latencies = []
    seen_ids = set()

    for _ in range(N):
        sent += 1
        req = Message(code=Code.GET, uri=URI, mtype=mtype)
        t0 = time.perf_counter()
        try:
            resp = await asyncio.wait_for(client.request(req).response, timeout=5.0)
            lat = (time.perf_counter() - t0) * 1000
            mid = resp.mid
            if mid in seen_ids:
                dupes += 1
            else:
                seen_ids.add(mid)
                received += 1
                latencies.append(lat)
        except Exception:
            pass
        await asyncio.sleep(0.05)

    lost    = sent - received
    loss_pct = round(lost / sent * 100, 1)
    avg_lat  = round(sum(latencies) / len(latencies), 1) if latencies else 0.0
    print(f"{label:<12}  sent={sent}  received={received}  lost={lost}"
          f"  loss={loss_pct}%  dupes={dupes}  avg_lat={avg_lat}ms")
    return sent, received, lost, loss_pct, dupes, avg_lat


async def main():
    server = await build_server()
    await asyncio.sleep(0.5)          # let server settle
    client = await aiocoap.Context.create_client_context()
    await asyncio.sleep(0.2)

    print(f"\n{'='*68}")
    print(f"  CoAP QoS Comparison  (N={N} requests per type, loopback)")
    print(f"{'='*68}")
    await measure(client, Type.NON, "CoAP NON")
    await measure(client, Type.CON, "CoAP CON")
    print(f"{'='*68}\n")

    await client.shutdown()
    await server.shutdown()


asyncio.run(main())
