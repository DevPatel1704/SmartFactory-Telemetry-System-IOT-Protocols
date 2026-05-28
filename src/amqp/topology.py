"""
Module 1 Assignment — Task 3.1
AMQP Broker Topology Declaration

Complete all TODO sections. Run this module once to set up the
RabbitMQ topology before running producer or consumer.

Run with:  python -m src.amqp.topology
"""

import logging
import ssl
import pika

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger(__name__)

# ── Connection parameters ─────────────────────────────────────────────────────
BROKER_HOST   = "localhost"
BROKER_PORT   = 5672          # plain AMQP (use 5671 for TLS in Tasks 3.2/3.3)
VHOST         = "/"
CREDENTIALS   = pika.PlainCredentials("guest", "guest")


def get_connection_params(host=BROKER_HOST, port=BROKER_PORT) -> pika.ConnectionParameters:
    return pika.ConnectionParameters(
        host=host, port=port,
        virtual_host=VHOST,
        credentials=CREDENTIALS,
        heartbeat=60,
    )


# ── Exchange names ─────────────────────────────────────────────────────────────
EXCHANGE_TELEMETRY = "iot.telemetry"   # main topic exchange
EXCHANGE_DLX       = "iot.dlx"         # dead letter exchange

# ── Queue names ────────────────────────────────────────────────────────────────
QUEUE_ALERTS      = "alerts-queue"
QUEUE_TEMPERATURE = "temperature-queue"
QUEUE_ALL         = "all-telemetry-queue"
QUEUE_DLX         = "dead-letter-queue"
QUEUE_LINE1       = "line1-queue"


def declare_topology(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
    """
    Declare all exchanges, queues, and bindings for the SmartFactory topology.
    This function is idempotent — safe to call multiple times.
    """

    # ── Exchanges ─────────────────────────────────────────────────────────────

    # TODO 1: Declare EXCHANGE_TELEMETRY as a durable topic exchange
    # channel.exchange_declare(...)
    raise NotImplementedError("TODO 1: declare iot.telemetry exchange")

    # TODO 2: Declare EXCHANGE_DLX as a durable direct exchange
    raise NotImplementedError("TODO 2: declare iot.dlx exchange")

    # ── Dead Letter Queue (declare before queues that reference it) ────────────

    # TODO 3: Declare QUEUE_DLX as a durable queue (no special arguments needed)
    raise NotImplementedError("TODO 3: declare dead-letter-queue")

    # TODO 4: Bind QUEUE_DLX to EXCHANGE_DLX with routing_key="dead"
    raise NotImplementedError("TODO 4: bind dead-letter-queue to iot.dlx")

    # ── Application Queues ────────────────────────────────────────────────────

    # TODO 5: Declare QUEUE_ALERTS — durable, bound to EXCHANGE_TELEMETRY with key "#.critical"
    # Arguments: none required
    raise NotImplementedError("TODO 5: declare and bind alerts-queue")

    # TODO 6: Declare QUEUE_TEMPERATURE — durable, with:
    #   x-message-ttl: 60000 (60 seconds)
    #   x-dead-letter-exchange: EXCHANGE_DLX
    #   x-dead-letter-routing-key: "dead"
    # Bind to EXCHANGE_TELEMETRY with key "*.*.temperature"
    raise NotImplementedError("TODO 6: declare and bind temperature-queue")

    # TODO 7: Declare QUEUE_ALL — durable, with:
    #   x-max-length: 10000
    #   x-overflow: "dead-letter"
    #   x-dead-letter-exchange: EXCHANGE_DLX
    # Bind to EXCHANGE_TELEMETRY with key "factory.#"
    raise NotImplementedError("TODO 7: declare and bind all-telemetry-queue")

    # TODO 8: Declare QUEUE_LINE1 — durable, no special arguments
    # Bind to EXCHANGE_TELEMETRY with key "factory.line1.#"
    raise NotImplementedError("TODO 8: declare and bind line1-queue")

    log.info("Topology declared successfully")


def setup() -> None:
    """Connect to RabbitMQ and declare the full topology."""
    params = get_connection_params()
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    try:
        declare_topology(channel)
    finally:
        connection.close()
    log.info("Topology setup complete. Check: http://localhost:15672")


if __name__ == "__main__":
    setup()
