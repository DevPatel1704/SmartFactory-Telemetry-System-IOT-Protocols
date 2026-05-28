"""
Module 1 Assignment — Task 3.2
AMQP Producer with Publisher Confirms

Complete all TODO sections.
"""

import json
import logging
import random
import ssl
import time
from datetime import datetime, timezone

import pika
import pika.exceptions

from src.amqp.topology import (
    EXCHANGE_TELEMETRY, QUEUE_TEMPERATURE,
    get_connection_params
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger(__name__)

CRITICAL_THRESHOLD = 85.0

SENSOR_CONFIG = {
    "temperature": {"unit": "C",    "base": 70.0, "noise": 3.0,  "persistent": True},
    "vibration":   {"unit": "mm/s", "base": 1.2,  "noise": 0.3,  "persistent": False},
    "power":       {"unit": "kW",   "base": 45.0, "noise": 5.0,  "persistent": True},
}
LINES = ["line1", "line2"]


class SmartFactoryProducer:

    def __init__(self):
        self._connection = None
        self._channel    = None
        self._published  = 0
        self._confirmed  = 0
        self._unconfirmed: set[int] = set()

    # ── Connection ─────────────────────────────────────────────────────────────

    def connect(self) -> None:
        """
        TODO 1: Connect to RabbitMQ and set up the channel with Publisher Confirms.
        Requirements:
          - Use get_connection_params() for connection parameters
          - Open a channel and call channel.confirm_delivery()
          - Register on_delivery_confirmed as the ack/nack callback:
              self._channel.add_on_return_callback(self.on_return)
              For confirms, use a nacks_callback — see pika docs for
              channel.add_on_ack_callback / add_on_nack_callback
        Note: pika BlockingConnection uses a simpler API — see pika docs for
              confirm_delivery() with the blocking adapter.
        """
        # TODO: implement this method
        raise NotImplementedError

    def disconnect(self) -> None:
        if self._connection and not self._connection.is_closed:
            self._connection.close()
        log.info("Producer stats — published: %d  confirmed: %d  unconfirmed: %d",
                 self._published, self._confirmed, len(self._unconfirmed))

    # ── Callbacks ──────────────────────────────────────────────────────────────

    def on_delivery_confirmed(self, method_frame) -> None:
        """
        TODO 2: Called when the broker sends a Basic.Ack or Basic.Nack.
        Requirements:
          - Extract the delivery_tag from method_frame.method.delivery_tag
          - If ACK: log "CONFIRM ack delivery_tag={tag}", increment _confirmed,
                    remove tag from _unconfirmed
          - If NACK: log "CONFIRM nack (LOST) delivery_tag={tag}" at WARNING level
        """
        # TODO: implement this callback
        pass

    def on_return(self, channel, method, properties, body) -> None:
        """
        TODO 3: Called when mandatory=True and no queue matched the routing key.
        Log: "RETURNED (no route): routing_key={method.routing_key} reply={method.reply_text}"
        """
        # TODO: implement this callback
        pass

    # ── Routing Key ────────────────────────────────────────────────────────────

    def _routing_key(self, line: str, sensor: str, value: float) -> str:
        """
        TODO 4: Build the AMQP routing key.
        Format: factory.{line}.{sensor}
        If sensor == "temperature" AND value > CRITICAL_THRESHOLD:
            Format: factory.{line}.temperature.critical
        Examples:
            factory.line1.temperature           (normal)
            factory.line1.temperature.critical  (> 85°C)
            factory.line2.vibration
        """
        # TODO: implement this method
        raise NotImplementedError

    # ── Publishing ─────────────────────────────────────────────────────────────

    def publish_reading(self, line: str, sensor: str) -> dict:
        """
        TODO 5: Simulate and publish a sensor reading.
        Requirements:
          - Simulate: value = cfg["base"] + random.gauss(0, cfg["noise"])
          - Build payload dict: {value, unit, line, sensor, timestamp, seq}
          - Set delivery_mode: 2 (persistent) if cfg["persistent"], else 1
          - Set expiration: "60000" (60 s TTL as string)
          - Set content_type: "application/json"
          - Set timestamp: int(time.time())
          - Publish to EXCHANGE_TELEMETRY with the correct routing key
          - Set mandatory=True
          - Track the delivery_tag in self._unconfirmed
          - Increment self._published
          - Log: "[{routing_key}]  val={value:.2f} {unit}  delivery_mode={mode}"
          - Return the payload dict
        """
        # TODO: implement this method
        raise NotImplementedError

    # ── Main Loop ──────────────────────────────────────────────────────────────

    def run(self, interval_s: float = 1.0) -> None:
        self.connect()
        seq = 0
        try:
            while True:
                seq += 1
                for line in LINES:
                    for sensor in SENSOR_CONFIG:
                        self.publish_reading(line, sensor)
                self._channel.connection.process_data_events()  # flush confirms
                time.sleep(interval_s)
        except KeyboardInterrupt:
            log.info("Shutting down…")
        finally:
            self.disconnect()


if __name__ == "__main__":
    producer = SmartFactoryProducer()
    producer.run()
