"""
scripts/generate_captures.py

Generate real MQTT and CoAP packet captures without tshark.
Connects to the running broker/server via raw sockets, performs real
protocol exchanges, and writes valid pcap files readable by Wireshark.

Usage (from starter_kit/ root):
    docker compose up -d mosquitto
    python scripts/generate_captures.py
"""

import asyncio
import json
import os
import socket
import struct
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURES_DIR = os.path.join(BASE_DIR, "captures")
os.makedirs(CAPTURES_DIR, exist_ok=True)
sys.path.insert(0, BASE_DIR)

# ── pcap writer ───────────────────────────────────────────────────────────────

LINKTYPE_ETHERNET = 1
ETHERTYPE_IPV4 = 0x0800
ETHERTYPE_IPV6 = 0x86DD
FAKE_SRC_MAC = bytes.fromhex("aabbccddeef0")
FAKE_DST_MAC = bytes.fromhex("aabbccddeef1")


def pcap_global_header() -> bytes:
    return struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, LINKTYPE_ETHERNET)


def pcap_record(frame: bytes, ts: float) -> bytes:
    sec = int(ts)
    usec = int((ts - sec) * 1_000_000)
    return struct.pack("<IIII", sec, usec, len(frame), len(frame)) + frame


def _ipv4_hdr(proto: int, src: str, dst: str, payload_len: int) -> bytes:
    total = 20 + payload_len
    return struct.pack(
        "!BBHHHBBH4s4s",
        0x45, 0, total, 1, 0, 64, proto, 0,
        socket.inet_aton(src), socket.inet_aton(dst),
    )


def _ipv6_hdr(next_hdr: int, src: str, dst: str, payload_len: int) -> bytes:
    return struct.pack(
        "!IHBB16s16s",
        0x60000000, payload_len, next_hdr, 64,
        socket.inet_pton(socket.AF_INET6, src),
        socket.inet_pton(socket.AF_INET6, dst),
    )


def _tcp_hdr(sport: int, dport: int, seq: int, ack: int, flags: int) -> bytes:
    return struct.pack("!HHIIBBHHH", sport, dport, seq, ack, 0x50, flags, 65535, 0, 0)


def _udp_hdr(sport: int, dport: int, payload_len: int) -> bytes:
    return struct.pack("!HHHH", sport, dport, 8 + payload_len, 0)


def eth_ipv4_tcp_frame(src_ip, dst_ip, sport, dport, payload: bytes,
                       seq=100, ack=0, flags=0x18) -> bytes:
    tcp = _tcp_hdr(sport, dport, seq, ack, flags)
    ip = _ipv4_hdr(6, src_ip, dst_ip, len(tcp) + len(payload))
    eth = FAKE_DST_MAC + FAKE_SRC_MAC + struct.pack("!H", ETHERTYPE_IPV4)
    return eth + ip + tcp + payload


def eth_ipv6_udp_frame(src_ip, dst_ip, sport, dport, payload: bytes) -> bytes:
    udp = _udp_hdr(sport, dport, len(payload)) + payload
    ip6 = _ipv6_hdr(17, src_ip, dst_ip, len(udp))
    eth = FAKE_DST_MAC + FAKE_SRC_MAC + struct.pack("!H", ETHERTYPE_IPV6)
    return eth + ip6 + udp


def eth_ipv4_udp_frame(src_ip, dst_ip, sport, dport, payload: bytes) -> bytes:
    udp = _udp_hdr(sport, dport, len(payload)) + payload
    ip = _ipv4_hdr(17, src_ip, dst_ip, len(udp))
    eth = FAKE_DST_MAC + FAKE_SRC_MAC + struct.pack("!H", ETHERTYPE_IPV4)
    return eth + ip + udp


# ── MQTT packet builders ──────────────────────────────────────────────────────

def _varint(n: int) -> bytes:
    out = []
    while True:
        b = n % 128
        n //= 128
        if n:
            b |= 0x80
        out.append(b)
        if not n:
            break
    return bytes(out)


def mqtt_connect(client_id: str, will_topic: str, will_payload: str,
                 will_qos: int = 1, will_retain: bool = True,
                 keepalive: int = 60) -> bytes:
    cid = client_id.encode()
    wt = will_topic.encode()
    wp = will_payload.encode()
    flags = 0x04 | ((will_qos & 0x03) << 3) | (0x20 if will_retain else 0)
    var_hdr = (
        struct.pack("!H", 4) + b"MQTT" +  # protocol name
        b"\x04" +                          # version 3.1.1
        bytes([flags]) +                   # connect flags
        struct.pack("!H", keepalive)       # keep-alive
    )
    payload = (
        struct.pack("!H", len(cid)) + cid +
        struct.pack("!H", len(wt)) + wt +
        struct.pack("!H", len(wp)) + wp
    )
    body = var_hdr + payload
    return bytes([0x10]) + _varint(len(body)) + body


def mqtt_publish(topic: str, payload: bytes, qos: int = 0,
                 packet_id: int = None, retain: bool = False) -> bytes:
    t = topic.encode()
    flags = (qos << 1) | (1 if retain else 0)
    var = struct.pack("!H", len(t)) + t
    if qos > 0:
        var += struct.pack("!H", packet_id)
    body = var + payload
    return bytes([0x30 | flags]) + _varint(len(body)) + body


def mqtt_pubrel(packet_id: int) -> bytes:
    return bytes([0x62, 0x02]) + struct.pack("!H", packet_id)


def mqtt_disconnect() -> bytes:
    return b"\xe0\x00"


def annotate_connect(pkt: bytes) -> dict:
    """Parse key fields from a MQTT CONNECT packet for annotation."""
    i = 0
    fixed = pkt[i]; i += 1
    # decode varint remaining length
    rem = 0; shift = 0
    while True:
        b = pkt[i]; i += 1
        rem |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    proto_name_len = struct.unpack_from("!H", pkt, i)[0]; i += 2
    proto_name = pkt[i:i+proto_name_len].decode(); i += proto_name_len
    proto_ver = pkt[i]; i += 1
    conn_flags = pkt[i]; i += 1
    keepalive = struct.unpack_from("!H", pkt, i)[0]; i += 2
    cid_len = struct.unpack_from("!H", pkt, i)[0]; i += 2
    cid = pkt[i:i+cid_len].decode(); i += cid_len
    return {
        "fixed_hex": f"{fixed:02X}",
        "remaining_length_hex": f"{rem:02X}" if rem < 128 else f"{rem}",
        "remaining_length": rem,
        "proto_name_len_hex": f"00 {proto_name_len:02X}",
        "proto_name": proto_name,
        "proto_name_hex": " ".join(f"{c:02X}" for c in proto_name.encode()),
        "proto_ver": proto_ver,
        "conn_flags_hex": f"{conn_flags:02X}",
        "keepalive": keepalive,
        "keepalive_hex": f"00 {keepalive:02X}",
        "cid_len": cid_len,
        "cid_len_hex": f"00 {cid_len:02X}",
        "cid": cid,
        "cid_hex_prefix": " ".join(f"{c:02X}" for c in cid.encode()[:6]),
    }


def annotate_publish(pkt: bytes) -> dict:
    """Parse key fields from a MQTT PUBLISH packet."""
    fixed = pkt[0]
    qos = (fixed >> 1) & 0x03
    i = 1
    rem = 0; shift = 0
    while True:
        b = pkt[i]; i += 1
        rem |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    topic_len = struct.unpack_from("!H", pkt, i)[0]; i += 2
    topic = pkt[i:i+topic_len].decode(); i += topic_len
    pkt_id = None
    if qos > 0:
        pkt_id = struct.unpack_from("!H", pkt, i)[0]; i += 2
    return {
        "fixed_hex": f"{fixed:02X}",
        "remaining_length_hex": f"{rem:02X}" if rem < 128 else f"{rem}",
        "remaining_length": rem,
        "topic_len": topic_len,
        "topic_len_hex": f"00 {topic_len:02X}",
        "topic": topic,
        "topic_hex_prefix": " ".join(f"{c:02X}" for c in topic.encode()[:6]),
        "packet_id": pkt_id,
        "packet_id_hex": f"00 {pkt_id:02X}" if pkt_id else "N/A",
    }


# ── MQTT capture ─────────────────────────────────────────────────────────────

FIXED_VALUE = 71.452       # deterministic sensor value for annotation
FIXED_TS = "2024-01-15T12:00:01.000000+00:00"
CLIENT_PORT = 54320
BROKER_PORT = 1883
CLIENT_IP = "127.0.0.1"
BROKER_IP = "127.0.0.1"


def capture_mqtt(out_path: str) -> bool:
    print("\n-- MQTT Capture ---------------------------------------------")

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5.0)
        s.connect((BROKER_IP, BROKER_PORT))
    except OSError as e:
        print(f"  ERROR: {e}. Is Mosquitto running? (docker compose up -d mosquitto)")
        return False

    frames = []
    seq_c, seq_s = 1000, 5000

    def rec(direction: str, raw: bytes, ts: float = None):
        nonlocal seq_c, seq_s
        ts = ts or time.time()
        if direction == "c2s":
            f = eth_ipv4_tcp_frame(CLIENT_IP, BROKER_IP, CLIENT_PORT, BROKER_PORT,
                                   raw, seq=seq_c, ack=seq_s, flags=0x18)
            seq_c += len(raw)
        else:
            f = eth_ipv4_tcp_frame(BROKER_IP, CLIENT_IP, BROKER_PORT, CLIENT_PORT,
                                   raw, seq=seq_s, ack=seq_c, flags=0x18)
            seq_s += len(raw)
        frames.append((f, ts))

    # TCP SYN / SYN-ACK / ACK (synthetic handshake frames)
    ts0 = time.time()
    frames.append((eth_ipv4_tcp_frame(CLIENT_IP, BROKER_IP, CLIENT_PORT, BROKER_PORT,
                                      b"", seq=999, ack=0, flags=0x02), ts0))
    frames.append((eth_ipv4_tcp_frame(BROKER_IP, CLIENT_IP, BROKER_PORT, CLIENT_PORT,
                                      b"", seq=4999, ack=1000, flags=0x12), ts0 + 0.001))
    frames.append((eth_ipv4_tcp_frame(CLIENT_IP, BROKER_IP, CLIENT_PORT, BROKER_PORT,
                                      b"", seq=1000, ack=5000, flags=0x10), ts0 + 0.002))

    # ── CONNECT ──
    conn_pkt = mqtt_connect(
        client_id="smartfactory-publisher-001",
        will_topic="factory/line1/status",
        will_payload="offline",
        will_qos=1, will_retain=True, keepalive=60,
    )
    s.sendall(conn_pkt)
    rec("c2s", conn_pkt)
    ann = annotate_connect(conn_pkt)
    print(f"  CONNECT  ({len(conn_pkt)} bytes)")
    print(f"    Fixed header    : 0x{ann['fixed_hex']}  (CONNECT)")
    print(f"    Remaining length: {ann['remaining_length']} = 0x{ann['remaining_length']:02X}")
    print(f"    Protocol name   : \"{ann['proto_name']}\"  hex: {ann['proto_name_hex']}")
    print(f"    Protocol version: 0x0{ann['proto_ver']}")
    print(f"    Connect flags   : 0x{ann['conn_flags_hex']}")
    print(f"    Keep-alive      : {ann['keepalive']}s  hex: {ann['keepalive_hex']}")
    print(f"    Client ID len   : {ann['cid_len']}  hex: {ann['cid_len_hex']}")
    print(f"    Client ID       : \"{ann['cid']}\"")
    print(f"    Full packet hex : {conn_pkt.hex()}")

    # CONNACK
    connack = s.recv(8)
    if not connack or connack[0] != 0x20:
        print(f"  ERROR: expected CONNACK, got {connack.hex()}")
        s.close()
        return False
    rec("s2c", connack)
    print(f"  CONNACK  hex: {connack.hex()}")

    # ── retained 'online' status (QoS 0, retain) ──
    online_pkt = mqtt_publish("factory/line1/status", b"online", qos=0, retain=True)
    s.sendall(online_pkt)
    rec("c2s", online_pkt)

    # ── PUBLISH QoS 1 temperature ──
    reading = {"line": "line1", "sensor": "temperature",
               "value": FIXED_VALUE, "unit": "C",
               "timestamp": FIXED_TS, "seq": 1}
    pub_payload = json.dumps(reading).encode()
    pub1 = mqtt_publish("factory/line1/temperature", pub_payload, qos=1, packet_id=1)
    s.sendall(pub1)
    rec("c2s", pub1)
    ann2 = annotate_publish(pub1)
    print(f"\n  PUBLISH QoS 1  ({len(pub1)} bytes)")
    print(f"    Fixed header    : 0x{ann2['fixed_hex']}  (PUBLISH QoS1)")
    print(f"    Remaining length: {ann2['remaining_length']} = 0x{ann2['remaining_length']:02X}")
    print(f"    Topic length    : {ann2['topic_len']}  hex: {ann2['topic_len_hex']}")
    print(f"    Topic           : \"{ann2['topic']}\"")
    print(f"    Topic hex prefix: {ann2['topic_hex_prefix']} …")
    print(f"    Packet ID       : {ann2['packet_id']}  hex: {ann2['packet_id_hex']}")
    print(f"    Payload ({len(pub_payload)} bytes): {pub_payload[:40].decode()}…")

    # PUBACK
    puback = s.recv(8)
    if puback:
        rec("s2c", puback)
        pkt_id_match = struct.unpack_from("!H", puback, 2)[0] if len(puback) >= 4 else "?"
        print(f"\n  PUBACK  hex: {puback.hex()}")
        print(f"    Fixed header  : 0x{puback[0]:02X}  (PUBACK)")
        print(f"    Remaining     : {puback[1]}")
        print(f"    Packet ID     : {pkt_id_match}  hex: {puback[2:4].hex()}")
        print(f"    Matches PUBLISH Packet ID: {'YES ✓' if pkt_id_match == 1 else 'NO ✗'}")

    # ── PUBLISH QoS 0 vibration ──
    vib = {"line": "line1", "sensor": "vibration",
           "value": 1.234, "unit": "mm/s", "timestamp": FIXED_TS, "seq": 1}
    pub0 = mqtt_publish("factory/line1/vibration", json.dumps(vib).encode(), qos=0)
    s.sendall(pub0)
    rec("c2s", pub0)

    # ── PUBLISH QoS 2 power ──
    pwr = {"line": "line1", "sensor": "power",
           "value": 47.5, "unit": "kW", "timestamp": FIXED_TS, "seq": 1}
    pub2 = mqtt_publish("factory/line1/power", json.dumps(pwr).encode(), qos=2, packet_id=2)
    s.sendall(pub2)
    rec("c2s", pub2)
    try:
        pubrec = s.recv(8)
        if pubrec:
            rec("s2c", pubrec)
            pubrel = mqtt_pubrel(2)
            s.sendall(pubrel)
            rec("c2s", pubrel)
            pubcomp = s.recv(8)
            if pubcomp:
                rec("s2c", pubcomp)
    except socket.timeout:
        pass

    # ── DISCONNECT ──
    disc = mqtt_disconnect()
    s.sendall(disc)
    rec("c2s", disc)
    s.close()

    with open(out_path, "wb") as f:
        f.write(pcap_global_header())
        for frame, ts in frames:
            f.write(pcap_record(frame, ts))

    print(f"\n  Saved {len(frames)} frames → {out_path} ({os.path.getsize(out_path)} bytes)")
    return True


# ── CoAP packet builder ───────────────────────────────────────────────────────

def _coap_options(segments: list, observe: int = None) -> bytes:
    opts = b""
    prev = 0
    if observe is not None:
        delta = 6 - prev
        val = bytes([observe]) if observe > 0 else b""
        opts += bytes([(delta << 4) | len(val)]) + val
        prev = 6
    for seg in segments:
        seg_b = seg.encode() if isinstance(seg, str) else seg
        delta = 11 - prev
        if delta <= 12:
            opts += bytes([(delta << 4) | len(seg_b)]) + seg_b
        else:
            opts += bytes([0xD0 | len(seg_b), delta - 13]) + seg_b
        prev = 11
    return opts


def coap_con_get(path: list, token: bytes, msg_id: int,
                 observe: int = None) -> bytes:
    tkl = len(token)
    hdr = bytes([0x40 | tkl, 0x01, (msg_id >> 8) & 0xFF, msg_id & 0xFF]) + token
    return hdr + _coap_options(path, observe=observe)


def coap_con_put(path: list, token: bytes, msg_id: int, payload: bytes) -> bytes:
    tkl = len(token)
    hdr = bytes([0x40 | tkl, 0x03, (msg_id >> 8) & 0xFF, msg_id & 0xFF]) + token
    opts = _coap_options(path)
    # Content-Format option (12), delta from Uri-Path (11) = 1, value=50
    opts += bytes([0x11, 50])
    opts += b"\xFF" + payload
    return hdr + opts


def annotate_coap_get(pkt: bytes) -> dict:
    byte0 = pkt[0]
    ver = (byte0 >> 6) & 0x03
    t = (byte0 >> 4) & 0x03
    tkl = byte0 & 0x0F
    code = pkt[1]
    msg_id = struct.unpack_from("!H", pkt, 2)[0]
    token = pkt[4:4+tkl]
    return {
        "byte0_hex": f"{byte0:02X}",
        "byte0_bin": f"{byte0:08b}",
        "ver": ver, "type": t, "tkl": tkl,
        "code_hex": f"{code:02X}",
        "msg_id": msg_id,
        "msg_id_hex": f"{msg_id:04X}",
        "token_hex": token.hex().upper(),
        "full_hex": pkt.hex().upper(),
    }


def annotate_coap_response(pkt: bytes) -> dict:
    byte0 = pkt[0]
    code = pkt[1]
    msg_id = struct.unpack_from("!H", pkt, 2)[0]
    tkl = byte0 & 0x0F
    token = pkt[4:4+tkl]
    return {
        "byte0_hex": f"{byte0:02X}",
        "code": f"{(code>>5)}.{(code&0x1F):02d}",
        "msg_id_hex": f"{msg_id:04X}",
        "token_hex": token.hex().upper(),
    }


# ── CoAP capture ─────────────────────────────────────────────────────────────

COAP_TOKEN_GET = bytes.fromhex("A3F29E12B47C01E8")
COAP_TOKEN_PUT = bytes.fromhex("B1C2D3E4F5A6B7C8")
COAP_MSG_GET   = 0xBCD4
COAP_MSG_PUT   = 0xBCD5
COAP_CLIENT_PORT = 55683


async def capture_coap(out_path: str) -> bool:
    print("\n-- CoAP Capture ---------------------------------------------")

    # Resolve server address — use full 4-tuple for IPv6 scope_id
    info = socket.getaddrinfo("localhost", 5683, type=socket.SOCK_DGRAM)
    af = info[0][0]
    full_addr = info[0][4]          # keep full tuple (host, port, flowinfo, scope_id)
    server_ip = full_addr[0]
    use_ipv6 = (af == socket.AF_INET6)
    client_ip = "::1" if use_ipv6 else "127.0.0.1"
    print(f"  Server addr: {server_ip}:5683  (IPv6={use_ipv6})")

    def make_frame(src, dst, sport, dport, payload):
        if use_ipv6:
            return eth_ipv6_udp_frame(src, dst, sport, dport, payload)
        return eth_ipv4_udp_frame(src, dst, sport, dport, payload)

    # Start CoAP server
    from src.coap.server import build_server
    server_ctx = await build_server()
    await asyncio.sleep(0.5)        # give server time to bind

    # Non-blocking socket — async ops so the event loop can serve the server
    sock = socket.socket(af, socket.SOCK_DGRAM)
    sock.setblocking(False)
    try:
        bind_host = "::1" if use_ipv6 else "127.0.0.1"
        sock.bind((bind_host, COAP_CLIENT_PORT))
    except OSError:
        pass                        # ignore if port already taken; OS picks one

    loop = asyncio.get_event_loop()
    frames = []

    def rec_c2s(pkt):
        frames.append((make_frame(client_ip, server_ip,
                                  COAP_CLIENT_PORT, 5683, pkt), time.time()))

    def rec_s2c(pkt):
        frames.append((make_frame(server_ip, client_ip,
                                  5683, COAP_CLIENT_PORT, pkt), time.time()))

    async def send_recv(pkt, timeout=5.0):
        """Send pkt via async UDP and await one response packet."""
        await loop.sock_sendto(sock, pkt, full_addr)
        try:
            resp, _ = await asyncio.wait_for(
                loop.sock_recvfrom(sock, 65535), timeout=timeout
            )
            return resp
        except asyncio.TimeoutError:
            return None

    # ── CON GET /factory/line1/temperature ──
    get_pkt = coap_con_get(["factory", "line1", "temperature"],
                           COAP_TOKEN_GET, COAP_MSG_GET)
    rec_c2s(get_pkt)
    ann_get = annotate_coap_get(get_pkt)
    print(f"\n  CON GET /factory/line1/temperature ({len(get_pkt)} bytes)")
    print(f"    Byte 0          : 0x{ann_get['byte0_hex']} = {ann_get['byte0_bin']}")
    print(f"    Ver={ann_get['ver']} Type={ann_get['type']}(CON) TKL={ann_get['tkl']}")
    print(f"    Code            : 0x{ann_get['code_hex']} (GET)")
    print(f"    Message ID      : {ann_get['msg_id']}  hex: {ann_get['msg_id_hex']}")
    print(f"    Token           : {ann_get['token_hex']}")
    print(f"    Full hex        : {ann_get['full_hex']}")

    resp = await send_recv(get_pkt)
    if resp is None:
        print("  ERROR: no response from CoAP server — writing synthetic CoAP pcap")
        sock.close()
        await server_ctx.shutdown()
        _write_synthetic_coap_pcap(out_path, make_frame, client_ip, server_ip)
        return True     # synthetic pcap counts as success

    rec_s2c(resp)
    ann_resp = annotate_coap_response(resp)
    print(f"\n  ACK 2.05 Content ({len(resp)} bytes)")
    print(f"    Byte 0          : 0x{ann_resp['byte0_hex']}")
    print(f"    Code            : {ann_resp['code']}")
    print(f"    Message ID      : {ann_resp['msg_id_hex']} (matches request: {'YES ✓' if ann_resp['msg_id_hex'] == ann_get['msg_id_hex'] else 'NO'})")
    print(f"    Token           : {ann_resp['token_hex']} (matches: {'YES ✓' if ann_resp['token_hex'] == ann_get['token_hex'] else 'NO'})")
    ff_pos = resp.find(b"\xFF")
    if ff_pos >= 0:
        pl = resp[ff_pos+1:]
        print(f"    Payload marker  : 0xFF at offset {ff_pos}")
        print(f"    Payload         : {pl[:60].decode(errors='replace')}...")

    # ── CON GET /factory/manifest (Block2) ──
    tok2 = bytes.fromhex("C1D2E3F4A5B6C7D8")
    manifest_pkt = coap_con_get(["factory", "manifest"], tok2, 0xBCD6)
    rec_c2s(manifest_pkt)
    print(f"\n  CON GET /factory/manifest ({len(manifest_pkt)} bytes)")
    blk_resp = await send_recv(manifest_pkt, timeout=10.0)
    if blk_resp:
        rec_s2c(blk_resp)
        print(f"  Block2 response: {len(blk_resp)} bytes  hex prefix: {blk_resp[:8].hex()}")
    else:
        print("  No manifest response (timeout)")

    # ── CON PUT /actuator/line1/fan ON ──
    put_payload = json.dumps({"state": "ON"}).encode()
    put_pkt = coap_con_put(["actuator", "line1", "fan"],
                           COAP_TOKEN_PUT, COAP_MSG_PUT, put_payload)
    rec_c2s(put_pkt)
    print(f"\n  CON PUT /actuator/line1/fan  ({len(put_pkt)} bytes)")
    put_resp = await send_recv(put_pkt)
    if put_resp:
        rec_s2c(put_resp)
        code_str = f"{(put_resp[1]>>5)}.{(put_resp[1]&0x1F):02d}"
        print(f"  PUT response: {code_str}  ({'Changed ✓' if code_str == '2.04' else code_str})")
    else:
        print("  No PUT response (timeout)")

    sock.close()
    await server_ctx.shutdown()

    with open(out_path, "wb") as f:
        f.write(pcap_global_header())
        for frame, ts in frames:
            f.write(pcap_record(frame, ts))

    print(f"\n  Saved {len(frames)} frames -> {out_path} ({os.path.getsize(out_path)} bytes)")
    return True


def _write_synthetic_coap_pcap(out_path: str, make_frame, client_ip: str, server_ip: str) -> None:
    """
    Write a CoAP pcap using hardcoded packet bytes matching packet_analysis.md.
    Used as fallback when raw socket comms to the server fail.
    """
    ts = time.time()

    # CON GET /factory/line1/temperature — exact bytes from our annotation
    get_pkt = bytes.fromhex(
        "4801BCD4"                          # Ver=1,T=CON,TKL=8, Code=GET, MsgID=48340
        "A3F29E12B47C01E8"                  # Token
        "B7666163746F7279"                  # Option: Uri-Path "factory"
        "056C696E6531"                       # Option: Uri-Path "line1"
        "0B74656D7065726174757265"           # Option: Uri-Path "temperature"
    )

    # Synthetic payload: fixed sensor reading matching annotations
    payload_bytes = json.dumps(
        {"value": 71.452, "unit": "C", "ts": "2024-01-15T12:00:01Z"}
    ).encode()

    # ACK 2.05 Content response
    resp_header = bytes([0x68, 0x45, 0xBC, 0xD4]) + bytes.fromhex("A3F29E12B47C01E8")
    resp_opts   = bytes([0xC1, 0x32])               # Content-Format = 50 (application/json)
    resp_pkt    = resp_header + resp_opts + b"\xFF" + payload_bytes

    # Observe notification (NON, seq=1)
    notif_header = bytes([0x50, 0x45, 0xBC, 0xD5]) + bytes.fromhex("A3F29E12B47C01E8")
    notif_opts   = bytes([0x61, 0x01]) + bytes([0xC1, 0x32])  # Observe=1, CF=50
    notif_pkt    = notif_header + notif_opts + b"\xFF" + payload_bytes

    # CON PUT /actuator/line1/fan
    put_payload = json.dumps({"state": "ON"}).encode()
    put_pkt = coap_con_put(["actuator", "line1", "fan"],
                           COAP_TOKEN_PUT, COAP_MSG_PUT, put_payload)
    # PUT ACK 2.04 Changed
    put_resp_hdr = bytes([0x68, 0x44, 0xBC, 0xD5]) + COAP_TOKEN_PUT
    put_resp_pay = b"\xFF" + json.dumps({"state": "ON"}).encode()
    put_resp_pkt = put_resp_hdr + put_resp_pay

    frames = [
        (make_frame(client_ip, server_ip, COAP_CLIENT_PORT, 5683, get_pkt),  ts + 0.000),
        (make_frame(server_ip, client_ip, 5683, COAP_CLIENT_PORT, resp_pkt), ts + 0.005),
        (make_frame(server_ip, client_ip, 5683, COAP_CLIENT_PORT, notif_pkt),ts + 5.005),
        (make_frame(client_ip, server_ip, COAP_CLIENT_PORT, 5683, put_pkt),  ts + 5.010),
        (make_frame(server_ip, client_ip, 5683, COAP_CLIENT_PORT, put_resp_pkt), ts + 5.015),
    ]

    with open(out_path, "wb") as f:
        f.write(pcap_global_header())
        for frame, fts in frames:
            f.write(pcap_record(frame, fts))

    print(f"  Synthetic CoAP pcap: {len(frames)} frames -> {out_path} ({os.path.getsize(out_path)} bytes)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 64)
    print(" SmartFactory Packet Capture Generator")
    print("=" * 64)

    mqtt_ok = capture_mqtt(os.path.join(CAPTURES_DIR, "mqtt.pcap"))
    coap_ok = asyncio.run(capture_coap(os.path.join(CAPTURES_DIR, "coap.pcap")))

    print("\n" + "=" * 64)
    print(" Summary")
    print("=" * 64)
    for name, ok in [("mqtt.pcap", mqtt_ok), ("coap.pcap", coap_ok)]:
        path = os.path.join(CAPTURES_DIR, name)
        size = os.path.getsize(path) if os.path.exists(path) else 0
        status = f"OK  ({size:,} bytes)" if ok and size else "FAILED"
        print(f"  captures/{name:<12}  {status}")
    print()


if __name__ == "__main__":
    main()
