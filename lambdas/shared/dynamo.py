"""DynamoDB write helper with retry logic.

Implements 3-retry exponential backoff for DynamoDB PutItem operations
as required by the platform's error handling strategy.

Writes are append-only (ADR-0005): every PutItem carries
``attribute_not_exists(record_type)``, so an existing item is never silently
replaced. The IAM deny on UpdateItem/DeleteItem does not cover that on its
own — PutItem onto an existing key is an overwrite. A retried invocation
re-writing the same record (only ``created_at`` differs) is accepted as
idempotent; any other difference is rejected. Because the table's sort
key is ``record_type``, AUDIT records are persisted under a per-event sort key
(``AUDIT#<created_at>#<action>#<id>``) so one run's audit events accumulate
instead of each replacing the last.
"""

import time
import uuid
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

_APPEND_ONLY_CONDITION = "attribute_not_exists(record_type)"


def _to_dynamo(value):
    """Recursively convert floats to Decimal — boto3 rejects Python floats."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_dynamo(v) for v in value]
    return value


def _with_unique_audit_key(item: dict) -> dict:
    if item.get("record_type") != "AUDIT":
        return item
    return {
        **item,
        "record_type": (
            f"AUDIT#{item.get('created_at', '')}#{item.get('action', '')}#{uuid.uuid4().hex[:12]}"
        ),
    }


def _is_same_record(table, item: dict) -> bool:
    """True when the stored item is the same record as ``item`` apart from its
    ``created_at`` — i.e. a retried invocation re-writing what an earlier
    attempt already wrote. Any other difference is a real overwrite attempt."""
    existing = table.get_item(
        Key={"run_id": item["run_id"], "record_type": item["record_type"]}
    ).get("Item")
    if not isinstance(existing, dict):
        return False

    def strip(d: dict) -> dict:
        return {k: v for k, v in d.items() if k != "created_at"}

    return strip(existing) == strip(item)


def write_item(table_name: str, item: dict, max_retries: int = 3) -> dict:
    """Write an item to DynamoDB with exponential backoff retry.

    Args:
        table_name: Name of the DynamoDB table.
        item: Dictionary representing the item to write.
        max_retries: Maximum number of retry attempts (default 3).

    Returns:
        The DynamoDB PutItem response dict.

    Raises:
        ClientError: If all retry attempts are exhausted, or immediately with
            ``ConditionalCheckFailedException`` if the key already holds a
            *different* record. Re-writing the same record (only ``created_at``
            differs, as on a Step Functions retry) returns ``{"idempotent": True}``.
    """
    client = boto3.resource("dynamodb").Table(table_name)
    item = _to_dynamo(_with_unique_audit_key(item))
    base_delay = 0.1  # 100ms
    backoff_factor = 2

    last_error: ClientError | None = None

    for attempt in range(max_retries):
        try:
            response = client.put_item(Item=item, ConditionExpression=_APPEND_ONLY_CONDITION)
            return response
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                if _is_same_record(client, item):
                    return {"idempotent": True}
                raise
            last_error = e
            if attempt < max_retries - 1:
                delay = base_delay * (backoff_factor ** attempt)
                time.sleep(delay)

    raise last_error  # type: ignore[misc]
