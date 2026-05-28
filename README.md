# SmartFactory IoT Protocol Integration
### Real-Time Data Analytics for IoT — Module 1 Assignment

**Student:** Dev Vimalkumar Patel  
**Student ID:** 101042729  
**Course:** Real-Time Data Analytics for IoT  

---

## Test Results

All automated tests pass:

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

Full output: [`test_result.txt`](test_result.txt)

> Proxy test suite updated to professor's 7-test version (adds ETag, Location, and line2 checks).

---

## What Was Built

### Task 1 — MQTT (`src/mqtt/`)
- **`publisher.py`** — Publishes all 6 sensors (3 types × 2 lines) at 1 Hz with correct QoS per sensor type (temperature=QoS1, vibration=QoS0, power=QoS2), persistent session, and LWT configured for `factory/line1/status`
- **`subscriber.py`** — Wildcard subscriber on `factory/#`, separate QoS-2 subscription on `factory/+/temperature`, CRITICAL ALERT detection at >85°C, 30-second message summary

### Task 2 — CoAP (`src/coap/`)
- **`server.py`** — 6 observable resources (`/factory/line{1,2}/{temperature,vibration,power}`), fan actuator (`/actuator/line1/fan` with PUT ON/OFF → 2.04 Changed), and a >33 KB firmware manifest at `/factory/manifest` triggering Block2 transfer
- **`observer.py`** — Concurrent Observe subscriptions on both temperature resources, stale-notification detection (RFC 7641 mod-2²⁴), clean deregistration after 60 s, Block2 manifest reassembly

### Task 3 — AMQP (`src/amqp/`)
- **`topology.py`** — Full RabbitMQ topology: `iot.telemetry` topic exchange, `iot.dlx` dead-letter exchange, 5 queues with correct TTL/max-length/DLX bindings  
- *Task 3 skipped for grading per instructor instruction*

### Task 4 — Packet Analysis (`report/packet_analysis.md`)
- MQTT CONNECT, QoS-1 PUBLISH, and PUBACK annotated with byte-level field breakdowns
- CoAP CON GET, ACK 2.05 Content, and Observe notification annotated

### Task 5 — Protocol Comparison Report (`report/comparison_report.md`)
- QoS comparison table with measured latencies (QoS0=2.7ms, QoS1=2.8ms, QoS2=7.0ms)
- CoAP–HTTP proxy option mapping (RFC 8075)
- Protocol recommendations for all 4 SmartFactory data paths
- Reflection on implementation challenges (~300 words)

---

## How to Run

### Prerequisites
- Python 3.10+
- Docker Desktop running

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Start MQTT broker
docker compose up -d mosquitto
```

### Run Tests
```bash
python -m pytest tests/mqtt/ tests/coap/ -v
```

### Run Individual Components
```bash
# MQTT
python -m src.mqtt.publisher      # Terminal 1
python -m src.mqtt.subscriber     # Terminal 2

# CoAP
python -m src.coap.server         # Terminal 1
python -m src.coap.observer       # Terminal 2
```

---

## Project Structure

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
└── README.md                    ← Brief run instructions
```

---

## Infrastructure

| Service | Port | Notes |
|---------|------|-------|
| Mosquitto MQTT | 1883 | `docker compose up -d mosquitto` |
| CoAP Server | 5683 | `python -m src.coap.server` |
| RabbitMQ | 5672 / 15672 | `docker compose up -d rabbitmq` |
