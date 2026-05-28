# SmartFactory IoT Protocol Integration
### Module 1 — Real-Time Data Analytics for IoT

**Student:** Dev Vimalkumar Patel  
**Student ID:** 101042729  
**Course:** Real-Time Data Analytics for IoT  

---

## Test Results

All 29 automated tests pass with 0 warnings:

```
29 passed in 35.51s
```

| Test Suite | Tests | Status |
|------------|-------|--------|
| MQTT Publisher (Task 1.1) | 6 | PASSED |
| MQTT Subscriber (Task 1.2) | 5 | PASSED |
| MQTT QoS Experiment (Task 1.3) | 1 | PASSED |
| CoAP Server (Task 2.1) | 10 | PASSED |
| CoAP-HTTP Proxy (Task 2.3) | 7 | PASSED |
| AMQP Topology (Task 3) | — | Skipped per instructor |

Full test output: [`test_result.txt`](test_result.txt)

> The CoAP proxy test suite covers all 7 checks including ETag mapping, Location header, and multi-line resource access.

---

## Implementation Overview

### Task 1 — MQTT (`src/mqtt/`)
- **`publisher.py`** — Simulates 6 factory sensors (3 sensor types across 2 production lines) publishing at 1 Hz. Each sensor uses the correct QoS level: temperature=QoS 1, vibration=QoS 0, power=QoS 2. Configured with a persistent session and Last Will Testament on `factory/line1/status`
- **`subscriber.py`** — Subscribes to all topics via `factory/#` wildcard plus a dedicated QoS-2 subscription on `factory/+/temperature`. Triggers CRITICAL ALERT when temperature exceeds 85°C and logs a rolling 30-second message summary

### Task 2 — CoAP (`src/coap/`)
- **`server.py`** — Serves 6 observable sensor endpoints at `/factory/line{1,2}/{temperature,vibration,power}`. Includes a fan actuator at `/actuator/line1/fan` accepting PUT ON/OFF and returning 2.04 Changed, plus a >33 KB firmware manifest at `/factory/manifest` that exercises Block2 fragmentation
- **`observer.py`** — Registers concurrent Observe subscriptions on both line temperature resources. Implements stale-notification rejection per RFC 7641 (mod-2²⁴ sequence comparison), graceful deregistration after 60 s, and Block2 manifest reassembly

### Task 3 — AMQP (`src/amqp/`)
- **`topology.py`** — Declares the full RabbitMQ topology: `iot.telemetry` topic exchange, `iot.dlx` dead-letter exchange, and 5 queues with TTL, max-length, and DLX bindings  
- *Grading for Task 3 waived per instructor guidance*

### Task 4 — Packet Analysis (`report/packet_analysis.md`)
- Byte-level field annotations for MQTT CONNECT, QoS-1 PUBLISH, and PUBACK packets
- Wire-level breakdown of CoAP CON GET request, ACK 2.05 Content response, and Observe notification

### Task 5 — Protocol Comparison (`report/comparison_report.md`)
- Measured QoS latency table: QoS0=2.7 ms, QoS1=2.8 ms, QoS2=7.0 ms
- CoAP-to-HTTP header translation per RFC 8075
- Protocol selection recommendations for all 4 SmartFactory data paths
- Technical reflection on implementation challenges

---

## Setup & Execution

### Requirements
- Python 3.10+
- Docker Desktop (running)

### Install & Start Broker
```bash
pip install -r requirements.txt
docker compose up -d mosquitto
```

### Run All Tests
```bash
python -m pytest tests/mqtt/ tests/coap/ -v
```

### Start Individual Components
```bash
# MQTT
python -m src.mqtt.publisher      # Terminal 1
python -m src.mqtt.subscriber     # Terminal 2

# CoAP
python -m src.coap.server         # Terminal 1
python -m src.coap.observer       # Terminal 2
```

---

## Repository Layout

```
module1-assignment/
├── src/
│   ├── mqtt/
│   │   ├── publisher.py         ← Task 1.1 (completed)
│   │   └── subscriber.py        ← Task 1.2 (completed)
│   ├── coap/
│   │   ├── server.py            ← Task 2.1 (completed)
│   │   └── observer.py          ← Task 2.2 (completed)
│   └── amqp/
│       └── topology.py          ← Task 3.1 (skipped per instructor)
├── captures/
│   ├── mqtt.pcap                ← Task 4 capture
│   ├── coap.pcap                ← Task 4 capture
│   └── amqp.pcap                ← Task 4 (skipped per instructor)
├── report/
│   ├── packet_analysis.md       ← Task 4 annotations
│   └── comparison_report.md     ← Task 5 report
├── tests/                       ← Do not modify
├── docker-compose.yml           ← Do not modify
└── README.md
```

---

## Services

| Service | Port | Command |
|---------|------|---------|
| Mosquitto MQTT | 1883 | `docker compose up -d mosquitto` |
| CoAP Server | 5683 | `python -m src.coap.server` |
| RabbitMQ | 5672 / 15672 | `docker compose up -d rabbitmq` |
