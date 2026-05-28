# Module 1 Assignment — SmartFactory IoT Protocol Integration

**Real-Time Data Analytics for IoT** · Graduate Course · Module 1

**Student:** Dev Vimalkumar Patel  (101042729) 

---

## Quick Start

```bash
# 1. Install dependencies and start Docker services
bash setup.sh

# 2. Read the full assignment specification
open Module1_Assignment.docx

# 3. Work through the tasks in order:
#    Task 1 → src/mqtt/publisher.py  + src/mqtt/subscriber.py
#    Task 2 → src/coap/server.py     + src/coap/observer.py
#    Task 3 → src/amqp/topology.py   + src/amqp/producer.py   + src/amqp/consumer.py
#    Task 4 → bash scripts/capture.sh → annotate report/packet_analysis.md
#    Task 5 → report/comparison_report.md

# 4. Run all tests before submitting
pytest tests/ -v --tb=short
```

---

## Repository Structure

```
module1-assignment/
├── src/
│   ├── mqtt/
│   │   ├── publisher.py      ← Task 1.1  Fill in all TODO sections
│   │   └── subscriber.py     ← Task 1.2  Fill in all TODO sections
│   ├── coap/
│   │   ├── server.py         ← Task 2.1  Fill in all TODO sections
│   │   └── observer.py       ← Task 2.2  Fill in all TODO sections
│   └── amqp/
│       ├── topology.py       ← Task 3.1  Fill in all TODO sections
│       ├── producer.py       ← Task 3.2  Fill in all TODO sections
│       └── consumer.py       ← Task 3.3  Fill in all TODO sections
│
├── tests/
│   ├── mqtt/
│   │   ├── test_publisher.py   ← Do not modify
│   │   └── test_qos_loss.py    ← Do not modify (run with -s for output table)
│   ├── coap/
│   │   └── test_server.py      ← Do not modify
│   └── amqp/
│       └── test_topology.py    ← Do not modify
│
├── report/
│   ├── packet_analysis.md    ← Task 4  Fill in the annotation tables
│   └── comparison_report.md  ← Task 5  Write your analysis here
│
├── captures/                 ← Task 4  pcap files go here (git-ignored)
├── scripts/
│   └── capture.sh            ← Task 4  Run to capture traffic
├── config/
│   └── mosquitto.conf        ← Mosquitto broker configuration
├── docker-compose.yml        ← Infrastructure: Mosquitto + RabbitMQ + InfluxDB
├── requirements.txt
├── pytest.ini
└── setup.sh                  ← Run this first
```

---

## Running Individual Components

```bash
# Task 1 — MQTT
python -m src.mqtt.publisher       # Terminal 1
python -m src.mqtt.subscriber      # Terminal 2

# Task 2 — CoAP
python -m src.coap.server          # Terminal 1
python -m src.coap.observer        # Terminal 2

# Task 3 — AMQP (run in order)
python -m src.amqp.topology        # Once — sets up RabbitMQ topology
python -m src.amqp.producer        # Terminal 1
python -m src.amqp.consumer        # Terminal 2

# Task 4 — Packet capture (with publisher/server running)
bash scripts/capture.sh
```

---

## Running Tests

```bash
# All tests
pytest tests/ -v

# Individual task tests
pytest tests/mqtt/ -v
pytest tests/coap/ -v
pytest tests/amqp/ -v

# QoS experiment with output table (Task 1.3)
pytest tests/mqtt/test_qos_loss.py -v -s
```

---

## Infrastructure

| Service | Port | URL |
|---------|------|-----|
| Mosquitto MQTT | 1883 | mqtt://localhost:1883 |
| RabbitMQ AMQP | 5672 | amqp://localhost:5672 |
| RabbitMQ Management | 15672 | http://localhost:15672 (guest/guest) |
| CoAP server (Python) | 5683 | coap://localhost:5683 |
| InfluxDB (optional) | 8086 | http://localhost:8086 |

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# View logs
docker compose logs -f mosquitto
docker compose logs -f rabbitmq
```

---

