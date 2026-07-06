"""Pure transformation logic: raw Pub/Sub payload -> typed product row.

This module deliberately imports nothing outside the standard library so the
unit tests run without installing any GCP dependencies.

Error philosophy:
- TransformError (malformed JSON, missing id): the message can never succeed,
  the caller should let Pub/Sub retry it into the dead-letter queue.
- Field-level problems (unparseable price, date, boolean): degrade gracefully
  to NULL instead of rejecting the whole product. For last_update the original
  string is always preserved in last_update_raw so nothing is lost.
"""

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime


class TransformError(ValueError):
    """The message cannot be transformed into a product row at all."""


def transform_message(payload, message_id=None):
    """Turn a raw Pub/Sub payload (bytes or str) into a typed row dict.

    Raises TransformError when the payload is not valid JSON, is not a JSON
    object, or has no usable product id.
    """
    if isinstance(payload, bytes):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TransformError(f"payload is not valid UTF-8: {exc}") from exc

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise TransformError(f"payload is not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise TransformError(
            f"payload is {type(parsed).__name__}, expected a JSON object"
        )

    product_id = str(parsed.get("id") or "").strip()
    if not product_id:
        raise TransformError("payload has no product id")

    last_update_raw = parsed.get("last_update")

    return {
        "id": product_id,
        "name": _optional_str(parsed.get("name")),
        "description": _optional_str(parsed.get("description")),
        "is_in_stock": parse_bool(parsed.get("is_in_stock")),
        "price": parse_price(parsed.get("price")),
        "last_update": parse_timestamp(last_update_raw)
        if isinstance(last_update_raw, str)
        else None,
        "last_update_raw": _optional_str(last_update_raw),
        "attributes": parse_attributes(parsed.get("attributes")),
        "message_id": _optional_str(message_id),
    }


def parse_timestamp(raw):
    """Parse the source's stringified datetime; return aware datetime or None.

    The sample message uses RFC 1123 style ("Mon, 17 Jun 2024 13:47:16 UTC"),
    but the date format is so often an issue that a few common fallbacks are attempted as well.
    """

    def _ensure_utc(parsed_date: datetime) -> datetime:
        if parsed_date.tzinfo is None:
            return parsed_date.replace(tzinfo=timezone.utc)
        return parsed_date.astimezone(timezone.utc)


    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()

    # RFC 1123 / RFC 2822: "Mon, 17 Jun 2024 13:47:16 UTC"
    try:
        parsed = parsedate_to_datetime(text)
        if parsed is not None:
            return _ensure_utc(parsed)
    except (TypeError, ValueError):
        pass

    # ISO 8601: "2024-06-17T13:47:16Z", "2024-06-17T13:47:16+02:00", ...
    try:
        return _ensure_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        pass

    # A defensive, potentially dead branch
    fallback_date_formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
    )
    for fmt in fallback_date_formats:
        try:
            return _ensure_utc(datetime.strptime(text, fmt))
        except ValueError:
            continue

    return None


def parse_bool(raw):
    """Parse the source's stringified boolean; return bool or None."""
    if isinstance(raw, str):
        lowered = raw.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False

    # A defensive, potentially dead branch
    if isinstance(raw, bool):
        return raw
    return None


def parse_price(raw):
    """Parse the source's stringified float into a decimal string, or None.

    The value is returned as a canonical string (not a float) because the
    target column is NUMERIC and binary floats would introduce rounding
    errors on monetary values.
    """

    # bool is an int subclass; reject explicitly
    if isinstance(raw, bool):
        return None

    if isinstance(raw, (int, float, str)):
        try:
            value = Decimal(str(raw).strip())
        except (InvalidOperation, ValueError):
            return None
        if not value.is_finite():
            return None
        return str(value)
    return None


def parse_attributes(raw):
    """Normalise the attributes array into [{'key': str, 'value': str}, ...].

    Entries that are not key/value objects are skipped rather than failing
    the whole message.
    """
    if not isinstance(raw, list):
        return []
    attributes = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        value = entry.get("value")
        if key is None and value is None:
            continue
        attributes.append(
            {
                "key": None if key is None else str(key),
                "value": None if value is None else str(value),
            }
        )
    return attributes


def _optional_str(raw):
    if raw is None:
        return None
    return str(raw)
