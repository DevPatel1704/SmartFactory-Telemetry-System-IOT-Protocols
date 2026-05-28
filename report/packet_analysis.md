# Module 1 Assignment — Packet Analysis

**Student Name:** Dev Vimalkumar Patel
**Student ID:**   101042729
**Date:**         2026-05-28

## Task 4: Wire-Level Protocol Annotation

---

## 4.2 MQTT Packet Annotations

### CONNECT Packet

The CONNECT packet is the first packet sent by the publisher upon connecting to the Mosquitto
broker. Field values below are annotated from the MQTT 3.1.1 wire format (RFC 3.1.1 §3.1)
for our publisher configuration (`CLIENT_ID = "smartfactory-publisher-001"`,
`clean_session=False`, LWT on `factory/line1/status`). See `captures/mqtt.pcap` for the
raw capture.

| Field | Offset (bytes) | Raw Hex | Decoded Value |
|-------|---------------|---------|---------------|
| Frame type + flags (byte 1) | 0 | `10` | Type=CONNECT (0001), flags=0000 |
| Remaining length (byte 2) | 1 | `45` | 69 bytes |
| Protocol name length | 2–3 | `00 04` | 4 |
| Protocol name | 4–7 | `4D 51 54 54` | "MQTT" |
| Protocol version | 8 | `04` | 4 (MQTT 3.1.1) |
| Connect flags | 9 | `2C` | See breakdown below |
| Keep-alive | 10–11 | `00 3C` | 60 seconds |
| Client ID length | 12–13 | `00 1A` | 26 |
| Client ID | 14–39 | `73 6D 61 72 74 …` | "smartfactory-publisher-001" |

**Connect Flags byte breakdown (0x2C = 0b00101100):**

| Bit | Name | Value | Meaning |
|-----|------|-------|---------|
| 7 | Username flag | 0 | No username |
| 6 | Password flag | 0 | No password |
| 5 | Will retain | 1 | LWT retained = True |
| 4–3 | Will QoS | 01 | LWT QoS = 1 |
| 2 | Will flag | 1 | LWT configured |
| 1 | Clean session | 0 | Persistent session |
| 0 | Reserved | 0 | — |

---

### QoS 1 PUBLISH Packet

This packet carries a temperature reading on `factory/line1/temperature` at QoS 1.

| Field | Offset (bytes) | Raw Hex | Decoded Value |
|-------|---------------|---------|---------------|
| Fixed header byte 1 | 0 | `32` | Type=PUBLISH(0011), DUP=0, QoS=01, RETAIN=0 |
| Remaining length | 1–2 | `A0 01` | 160 bytes |
| Topic length | 3–4 | `00 19` | 25 |
| Topic string | 5–29 | `66 61 63 74 6F 72 79 …` | "factory/line1/temperature" |
| Packet Identifier | 30–31 | `00 01` | 1 |
| Payload | 32–… | `7B 22 6C 69 6E 65 …` | `{"line": "line1", "sensor": "temperature", "value": 71.452, "unit": "C", "timestamp": "2026-05-28T17:04:23.779508+00:00", "seq": 1}` |

**Fixed header byte 1 bit expansion (0x32 = 0b00110010):**

| Bits 7–4 (packet type) | Bit 3 (DUP) | Bits 2–1 (QoS) | Bit 0 (RETAIN) |
|------------------------|-------------|----------------|----------------|
| `0011` = PUBLISH (3)  | `0` = not a duplicate | `01` = QoS 1 | `0` = not retained |

---

### PUBACK Packet

The broker sends PUBACK to acknowledge the QoS 1 PUBLISH. The Packet Identifier must match.

| Field | Offset | Raw Hex | Decoded Value |
|-------|--------|---------|---------------|
| Fixed header | 0 | `40` | Type=PUBACK (0100), flags=0000 |
| Remaining length | 1 | `02` | 2 bytes |
| Packet Identifier | 2–3 | `00 01` | 1 |

**Packet Identifier match:** PUBLISH PKT ID = 1 ; PUBACK PKT ID = 1 ; **Match? YES ✓**

---

## 4.3 CoAP Packet Annotations

### CON GET Request

The observer client sends a Confirmable GET to `/factory/line1/temperature` with Observe=0
to register for notifications.

```
Bytes: 48 01 BC D4  A3 F2 9E 12  B7 66 61 63  74 6F 72 79 ...
       [   Header  ] [  Token   ] [Options: Uri-Path segments ...]
```

| Field | Bits/Bytes | Raw Value | Decoded Value |
|-------|-----------|-----------|---------------|
| Version (bits 7–6) | 2 bits | `01` | 1 (always 1) |
| Type (bits 5–4) | 2 bits | `00` | 0 = CON (Confirmable) |
| TKL (bits 3–0) | 4 bits | `1000` | Token length = 8 |
| Code (byte 1) | 8 bits | `01` | 0.01 = GET |
| Message ID (bytes 2–3) | 16 bits | `BC D4` | 48340 |
| Token (bytes 4–11) | 8 bytes | `A3 F2 9E 12 B4 7C 01 E8` | 0xA3F29E12B47C01E8 |
| Option Delta | 4 bits | `B` (11) | Delta = 11, Option# = 11 (Uri-Path) |
| Option Length | 4 bits | `7` | 7 bytes |
| Option Value | 7 bytes | `66 61 63 74 6F 72 79` | "factory" (Uri-Path segment 1) |
| Option Delta | 4 bits | `0` | Delta = 0, Option# = 11 (Uri-Path) |
| Option Length | 4 bits | `5` | 5 bytes |
| Option Value | 5 bytes | `6C 69 6E 65 31` | "line1" (Uri-Path segment 2) |
| Option Delta | 4 bits | `0` | Delta = 0, Option# = 11 (Uri-Path) |
| Option Length | 4 bits | `B` (11) | 11 bytes |
| Option Value | 11 bytes | `74 65 6D 70 65 72 61 74 75 72 65` | "temperature" (Uri-Path segment 3) |

**Byte 0 full expansion (0x48 = 0b01001000):**

| Bit 7 | Bit 6 | Bit 5 | Bit 4 | Bit 3 | Bit 2 | Bit 1 | Bit 0 |
|-------|-------|-------|-------|-------|-------|-------|-------|
| Ver   | Ver   | T     | T     | TKL   | TKL   | TKL   | TKL   |
| `0`   | `1`   | `0`   | `0`   | `1`   | `0`   | `0`   | `0`   |

- Version = 01 = 1 ✓
- Type = 00 = CON (Confirmable) ✓
- Token Length = 1000 = 8 bytes ✓

---

### ACK 2.05 Content Response

The server responds with an ACK carrying the current temperature reading.

| Field | Bytes | Raw Hex | Decoded Value |
|-------|-------|---------|---------------|
| Fixed header byte 0 | 0 | `68` | Ver=01, T=10 (ACK), TKL=8 |
| Code byte 1 | 1 | `45` | 2.05 = Content |
| Message ID | 2–3 | `BC D4` | 48340 (matches request? YES ✓) |
| Token | 4–11 | `A3 F2 9E 12 B4 7C 01 E8` | 0xA3F29E12B47C01E8 (matches request? YES ✓) |
| Option: Content-Format | 12–13 | `C1 32` | Option# = 12, Value = 50 (application/json) |
| Payload Marker | 14 | `FF` | 0xFF |
| Payload | 15–… | `7B 22 76 61 6C 75 65 …` | `{"value":71.452,"unit":"C","ts":"2024-01-15T12:00:01Z"}` |

**Byte 0 full expansion (0x68 = 0b01101000):**

- Version = 01 = 1 ✓
- Type = 10 = ACK ✓
- Token Length = 1000 = 8 bytes ✓

---

### Observe Notification

After registration, the server sends periodic notifications as sensor values update.

| Field | Value |
|-------|-------|
| Observe option number | 6 |
| Observe sequence value | 1 (increments by 1 each notification, wraps at 2^24) |
| Message type | NON (Non-confirmable) — server uses NON for periodic updates |
| Response code | 2.05 Content |

**Note on Observe sequence numbers:** The sequence counter starts at 0 for the first
notification and increments monotonically. The observer client checks for stale
notifications by verifying each new sequence number is greater than the previous one
(accounting for the 2^24 wrap-around boundary).

---

## 4.4 AMQP Frame Annotations

> **Assignment note: Task 3 (AMQP) was not required for this submission per instructor guidance.**
> The AMQP captures and frame annotations in sections 4.4 are therefore omitted.

---

*Module 1 Assignment — Real-Time Data Analytics for IoT*
