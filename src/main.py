"""Cloud Run function (Gen 2) entry point.

Triggered by messages on the synthetic-data-generator Pub/Sub topic
(via an Eventarc trigger). Parses the product JSON, casts the stringified
types, and appends the typed row to BigQuery.

Ack/nack contract:
- Returning normally acknowledges the message.
- Raising any exception nacks it; Pub/Sub redelivers with backoff and,
  after max-delivery-attempts (5, configured on the subscription), routes
  the message to the dead-letter topic. That covers both poison messages
  (TransformError, will never succeed) and transient BigQuery outages
  (retry usually succeeds before dead-lettering).
"""

import base64
import logging

import functions_framework

from bq_writer import write_product
from transform import TransformError, transform_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@functions_framework.cloud_event
def handle_message(cloud_event):
    message = cloud_event.data["message"]
    message_id = message.get("messageId") or message.get("message_id") or ""
    payload = base64.b64decode(message.get("data") or b"")

    try:
        row = transform_message(payload, message_id=message_id)
    except TransformError as exc:
        logger.error(
            "Malformed message %s: %s | payload (truncated): %r",
            message_id,
            exc,
            payload[:512],
        )
        raise

    write_product(row)
    logger.info("Ingested product %s (message %s)", row["id"], message_id)
