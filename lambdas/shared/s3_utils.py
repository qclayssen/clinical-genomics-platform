"""S3 read/write helpers for Lambda handlers."""

import json

import boto3


def read_json(bucket: str, key: str) -> dict:
    """Read and parse a JSON object from S3.

    Args:
        bucket: S3 bucket name.
        key: Object key in the bucket.

    Returns:
        Parsed JSON as a Python dict.
    """
    client = boto3.client("s3")
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read().decode("utf-8")
    return json.loads(body)


def write_json(bucket: str, key: str, data: dict) -> None:
    """Write a Python dict as JSON to S3.

    Args:
        bucket: S3 bucket name.
        key: Object key in the bucket.
        data: Dictionary to serialize as JSON.
    """
    client = boto3.client("s3")
    body = json.dumps(data, indent=2).encode("utf-8")
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
    )


def write_bytes(
    bucket: str,
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> None:
    """Write raw bytes to S3.

    Args:
        bucket: S3 bucket name.
        key: Object key in the bucket.
        data: Bytes to write.
        content_type: MIME type for the object (default: application/octet-stream).
    """
    client = boto3.client("s3")
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
