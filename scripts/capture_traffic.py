"""
Packet capture script — saves MQTT and CoAP traffic to captures/mqtt.pcap
and captures/coap.pcap.

Requirements:
  1. Install Wireshark (includes Npcap + tshark):  https://www.wireshark.org/download.html
  2. pip install scapy

Usage (run from starter_kit/ root):
  # Terminal 1 — MQTT capture (run while publisher is active)
  python scripts/capture_traffic.py mqtt

  # Terminal 2 — start publisher
  docker compose up -d mosquitto
  python -m src.mqtt.publisher

  # Terminal 3 — CoAP capture (run while server + observer are active)
  python scripts/capture_traffic.py coap

  # Terminal 4 — CoAP server + observer
  python -m src.coap.server
  python -m src.coap.observer
"""

import sys
import os
import time

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "captures")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CAPTURE_SECONDS = 30


def capture_mqtt():
    from scapy.all import sniff, wrpcap
    out = os.path.join(OUTPUT_DIR, "mqtt.pcap")
    print(f"Capturing MQTT (TCP port 1883) for {CAPTURE_SECONDS}s → {out}")
    print("Start your MQTT publisher NOW in another terminal.")
    pkts = sniff(filter="tcp port 1883", timeout=CAPTURE_SECONDS)
    wrpcap(out, pkts)
    print(f"Saved {len(pkts)} packets to {out}")


def capture_coap():
    from scapy.all import sniff, wrpcap
    out = os.path.join(OUTPUT_DIR, "coap.pcap")
    print(f"Capturing CoAP (UDP port 5683) for {CAPTURE_SECONDS}s → {out}")
    print("Start your CoAP server and observer NOW in other terminals.")
    pkts = sniff(filter="udp port 5683", timeout=CAPTURE_SECONDS)
    wrpcap(out, pkts)
    print(f"Saved {len(pkts)} packets to {out}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "mqtt"
    if mode == "coap":
        capture_coap()
    else:
        capture_mqtt()
