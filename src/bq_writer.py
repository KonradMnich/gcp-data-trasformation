"""Write typed product rows to BigQuery via the Storage Write API.

Type mapping (proto -> BigQuery):
    string  -> STRING
    string  -> NUMERIC   (the API accepts canonical decimal strings)
    bool    -> BOOLEAN
    int64   -> TIMESTAMP (epoch microseconds, UTC)
"""

import os
import threading
from datetime import datetime, timezone

from google.cloud import bigquery_storage_v1
from google.cloud.bigquery_storage_v1 import types, writer
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

_FIELD = descriptor_pb2.FieldDescriptorProto
_lock = threading.Lock()
_write_client = None
_append_stream = None


def _add_field(message_proto, name, number, field_type=None, label=None, type_name=None):
    field = message_proto.field.add()
    field.name = name
    field.number = number
    field.type = field_type if field_type is not None else _FIELD.TYPE_STRING
    field.label = label if label is not None else _FIELD.LABEL_OPTIONAL
    if type_name:
        field.type_name = type_name


def _build_product_record_class():
    file_proto = descriptor_pb2.FileDescriptorProto()
    file_proto.name = "product_record.proto"
    # Storage Write API expects proto2 semantics for row messages.
    file_proto.syntax = "proto2"

    record = file_proto.message_type.add()
    record.name = "ProductRecord"

    attribute = record.nested_type.add()
    attribute.name = "Attribute"
    _add_field(attribute, "key", 1)
    _add_field(attribute, "value", 2)

    _add_field(record, "id", 1)
    _add_field(record, "name", 2)
    _add_field(record, "description", 3)
    _add_field(record, "is_in_stock", 4, field_type=_FIELD.TYPE_BOOL)
    _add_field(record, "price", 5)  # decimal string -> NUMERIC
    _add_field(record, "last_update", 6, field_type=_FIELD.TYPE_INT64)  # micros -> TIMESTAMP
    _add_field(record, "last_update_raw", 7)
    _add_field(
        record,
        "attributes",
        8,
        field_type=_FIELD.TYPE_MESSAGE,
        label=_FIELD.LABEL_REPEATED,
        type_name=".ProductRecord.Attribute",
    )
    _add_field(record, "message_id", 9)
    _add_field(record, "ingested_at", 10, field_type=_FIELD.TYPE_INT64)

    pool = descriptor_pool.DescriptorPool()
    pool.Add(file_proto)
    descriptor = pool.FindMessageTypeByName("ProductRecord")
    return message_factory.GetMessageClass(descriptor)


ProductRecord = _build_product_record_class()


def _table_path():
    project = os.environ["BQ_PROJECT"]
    dataset = os.environ.get("BQ_DATASET", "products")
    table = os.environ.get("BQ_TABLE", "products")
    return f"projects/{project}/datasets/{dataset}/tables/{table}"


def _create_append_stream():
    global _write_client
    if _write_client is None:
        _write_client = bigquery_storage_v1.BigQueryWriteClient()

    # The _default stream: committed writes, no stream lifecycle management,
    # and it is what the free-tier quota applies to.
    request_template = types.AppendRowsRequest()
    request_template.write_stream = f"{_table_path()}/_default"

    proto_descriptor = descriptor_pb2.DescriptorProto()
    ProductRecord.DESCRIPTOR.CopyToProto(proto_descriptor)
    proto_schema = types.ProtoSchema()
    proto_schema.proto_descriptor = proto_descriptor

    proto_data = types.AppendRowsRequest.ProtoData()
    proto_data.writer_schema = proto_schema
    request_template.proto_rows = proto_data

    return writer.AppendRowsStream(_write_client, request_template)


def _to_epoch_micros(value: datetime) -> int:
    return int(value.timestamp() * 1_000_000)


def _row_to_proto(row: dict) -> bytes:
    record = ProductRecord()
    record.id = row["id"]
    if row.get("name") is not None:
        record.name = row["name"]
    if row.get("description") is not None:
        record.description = row["description"]
    if row.get("is_in_stock") is not None:
        record.is_in_stock = row["is_in_stock"]
    if row.get("price") is not None:
        record.price = row["price"]
    if row.get("last_update") is not None:
        record.last_update = _to_epoch_micros(row["last_update"])
    if row.get("last_update_raw") is not None:
        record.last_update_raw = row["last_update_raw"]
    for attribute in row.get("attributes") or []:
        entry = record.attributes.add()
        if attribute.get("key") is not None:
            entry.key = attribute["key"]
        if attribute.get("value") is not None:
            entry.value = attribute["value"]
    if row.get("message_id") is not None:
        record.message_id = row["message_id"]
    record.ingested_at = _to_epoch_micros(datetime.now(timezone.utc))
    return record.SerializeToString()


def write_product(row: dict) -> None:
    """Append one typed row to the products table.

    The gRPC stream is created lazily and reused across invocations of the
    same function instance. On any send failure the stream is discarded so
    the next attempt starts fresh; the exception propagates so Pub/Sub
    redelivers the message.
    """
    global _append_stream

    serialized = _row_to_proto(row)

    with _lock:
        if _append_stream is None:
            _append_stream = _create_append_stream()
        stream = _append_stream

    proto_rows = types.ProtoRows()
    proto_rows.serialized_rows.append(serialized)
    proto_data = types.AppendRowsRequest.ProtoData()
    proto_data.rows = proto_rows
    request = types.AppendRowsRequest()
    request.proto_rows = proto_data

    try:
        stream.send(request).result(timeout=30)
    except Exception:
        with _lock:
            if _append_stream is stream:
                _append_stream = None
        try:
            stream.close()
        except Exception:
            pass
        raise
