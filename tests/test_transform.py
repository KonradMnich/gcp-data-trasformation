"""Unit tests for src/transform.py.

Standard library only - no GCP dependencies needed. Run from the repo root:
"""

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transform import (  # noqa: E402
    TransformError,
    parse_attributes,
    parse_bool,
    parse_price,
    parse_timestamp,
    transform_message,
)

# The exact sample message from the assignment PDF.
SAMPLE_MESSAGE = {
    "id": "57b2d226-4e29-4d00-a7cb-663a81d42229",
    "name": "asWWKWUogiEJS",
    "description": "Lorem ipsum praesent elit aenean ultricies pharetra etiam cubilia.",
    "is_in_stock": "false",
    "price": "873.06",
    "last_update": "Mon, 17 Jun 2024 13:47:16 UTC",
    "attributes": [
        {"key": "key-0", "value": "vulputate"},
        {"key": "key-1", "value": "ipsum"},
        {"key": "key-2", "value": "sociosqu"},
    ],
}


class TransformMessageTest(unittest.TestCase):
    def test_sample_message_from_assignment(self):
        row = transform_message(json.dumps(SAMPLE_MESSAGE), message_id="msg-1")

        self.assertEqual(row["id"], "57b2d226-4e29-4d00-a7cb-663a81d42229")
        self.assertEqual(row["name"], "asWWKWUogiEJS")
        self.assertIs(row["is_in_stock"], False)
        self.assertEqual(row["price"], "873.06")
        self.assertEqual(
            row["last_update"],
            datetime(2024, 6, 17, 13, 47, 16, tzinfo=timezone.utc),
        )
        self.assertEqual(row["last_update_raw"], "Mon, 17 Jun 2024 13:47:16 UTC")
        self.assertEqual(len(row["attributes"]), 3)
        self.assertEqual(
            row["attributes"][0], {"key": "key-0", "value": "vulputate"}
        )
        self.assertEqual(row["message_id"], "msg-1")

    def test_accepts_bytes_payload(self):
        row = transform_message(json.dumps(SAMPLE_MESSAGE).encode("utf-8"))
        self.assertEqual(row["id"], SAMPLE_MESSAGE["id"])

    def test_malformed_json_raises(self):
        with self.assertRaises(TransformError):
            transform_message("this is not valid json {")

    def test_non_object_json_raises(self):
        with self.assertRaises(TransformError):
            transform_message('["a", "list", "not", "an", "object"]')

    def test_missing_id_raises(self):
        message = dict(SAMPLE_MESSAGE)
        del message["id"]
        with self.assertRaises(TransformError):
            transform_message(json.dumps(message))

    def test_empty_id_raises(self):
        message = dict(SAMPLE_MESSAGE, id="   ")
        with self.assertRaises(TransformError):
            transform_message(json.dumps(message))

    def test_invalid_utf8_raises(self):
        with self.assertRaises(TransformError):
            transform_message(b"\xff\xfe not utf-8")

    def test_bad_price_becomes_none(self):
        message = dict(SAMPLE_MESSAGE, price="not-a-number")
        row = transform_message(json.dumps(message))
        self.assertIsNone(row["price"])

    def test_missing_optional_fields_become_none_or_empty(self):
        row = transform_message(json.dumps({"id": "p-1"}))
        self.assertEqual(row["id"], "p-1")
        self.assertIsNone(row["name"])
        self.assertIsNone(row["description"])
        self.assertIsNone(row["is_in_stock"])
        self.assertIsNone(row["price"])
        self.assertIsNone(row["last_update"])
        self.assertIsNone(row["last_update_raw"])
        self.assertEqual(row["attributes"], [])

    def test_unparseable_date_keeps_raw_string(self):
        message = dict(SAMPLE_MESSAGE, last_update="not a date at all")
        row = transform_message(json.dumps(message))
        self.assertIsNone(row["last_update"])
        self.assertEqual(row["last_update_raw"], "not a date at all")


class ParseTimestampTest(unittest.TestCase):
    def test_rfc1123_with_utc(self):
        self.assertEqual(
            parse_timestamp("Mon, 17 Jun 2024 13:47:16 UTC"),
            datetime(2024, 6, 17, 13, 47, 16, tzinfo=timezone.utc),
        )

    def test_rfc2822_with_offset(self):
        parsed = parse_timestamp("Mon, 17 Jun 2024 13:47:16 +0200")
        self.assertEqual(
            parsed, datetime(2024, 6, 17, 11, 47, 16, tzinfo=timezone.utc)
        )

    def test_iso8601_with_z_suffix(self):
        self.assertEqual(
            parse_timestamp("2024-06-17T13:47:16Z"),
            datetime(2024, 6, 17, 13, 47, 16, tzinfo=timezone.utc),
        )

    def test_iso8601_naive_assumed_utc(self):
        self.assertEqual(
            parse_timestamp("2024-06-17T13:47:16"),
            datetime(2024, 6, 17, 13, 47, 16, tzinfo=timezone.utc),
        )

    def test_plain_date(self):
        self.assertEqual(
            parse_timestamp("2024-06-17"),
            datetime(2024, 6, 17, tzinfo=timezone.utc),
        )

    def test_garbage_returns_none(self):
        self.assertIsNone(parse_timestamp("definitely not a date"))

    def test_empty_and_non_string_return_none(self):
        self.assertIsNone(parse_timestamp(""))
        self.assertIsNone(parse_timestamp("   "))
        self.assertIsNone(parse_timestamp(None))
        self.assertIsNone(parse_timestamp(12345))


class ParseBoolTest(unittest.TestCase):
    def test_string_variants(self):
        self.assertIs(parse_bool("true"), True)
        self.assertIs(parse_bool("True"), True)
        self.assertIs(parse_bool(" FALSE "), False)
        self.assertIs(parse_bool("false"), False)

    def test_native_bool_passthrough(self):
        self.assertIs(parse_bool(True), True)
        self.assertIs(parse_bool(False), False)

    def test_invalid_returns_none(self):
        self.assertIsNone(parse_bool("yes"))
        self.assertIsNone(parse_bool("1"))
        self.assertIsNone(parse_bool(None))
        self.assertIsNone(parse_bool(1))


class ParsePriceTest(unittest.TestCase):
    def test_valid_string_price(self):
        self.assertEqual(parse_price("873.06"), "873.06")

    def test_numeric_inputs(self):
        self.assertEqual(parse_price(10), "10")
        self.assertEqual(parse_price(9.5), "9.5")

    def test_whitespace_trimmed(self):
        self.assertEqual(parse_price("  42.00 "), "42.00")

    def test_invalid_returns_none(self):
        self.assertIsNone(parse_price("not-a-number"))
        self.assertIsNone(parse_price(""))
        self.assertIsNone(parse_price(None))
        self.assertIsNone(parse_price(True))

    def test_non_finite_returns_none(self):
        self.assertIsNone(parse_price("NaN"))
        self.assertIsNone(parse_price("Infinity"))


class ParseAttributesTest(unittest.TestCase):
    def test_valid_attributes(self):
        result = parse_attributes([{"key": "k", "value": "v"}])
        self.assertEqual(result, [{"key": "k", "value": "v"}])

    def test_non_list_returns_empty(self):
        self.assertEqual(parse_attributes(None), [])
        self.assertEqual(parse_attributes("nope"), [])
        self.assertEqual(parse_attributes({"key": "k"}), [])

    def test_junk_entries_skipped(self):
        result = parse_attributes(
            ["a string", 42, None, {"unrelated": "shape"}, {"key": "k", "value": "v"}]
        )
        self.assertEqual(result, [{"key": "k", "value": "v"}])

    def test_values_coerced_to_string(self):
        result = parse_attributes([{"key": 1, "value": 2.5}])
        self.assertEqual(result, [{"key": "1", "value": "2.5"}])

    def test_missing_value_kept_as_none(self):
        result = parse_attributes([{"key": "k"}])
        self.assertEqual(result, [{"key": "k", "value": None}])


if __name__ == "__main__":
    unittest.main()
