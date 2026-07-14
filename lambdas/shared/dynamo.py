"""DynamoDB write helper with retry logic.

Implements 3-retry exponential backoff for DynamoDB PutItem operations
as required by the platform's error handling strategy.
"""

import time

import boto3
from botocore.exceptions import ClientError


def write_item(table_name: str, item: dict, max_retries: int = 3) -> dict:
    """Write an item to DynamoDB with exponential backoff retry.

    Args:
        table_name: Name of the DynamoDB table.
        item: Dictionary representing the item to write.
        max_retries: Maximum number of retry attempts (default 3).

    Returns:
        The DynamoDB PutItem response dict.

    Raises:
        ClientError: If all retry attempts are exhausted.
    """
    client = boto3.resource("dynamodb").Table(table_name)
    base_delay = 0.1  # 100ms
    backoff_factor = 2

    last_error: ClientError | None = None

    for attempt in range(max_retries):
        try:
            response = client.put_item(Item=item)
            return response
        except ClientError as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = base_delay * (backoff_factor ** attempt)
                time.sleep(delay)

    raise last_error  # type: ignore[misc]
