# app/services/r2_client.py
import os
import boto3
from botocore.config import Config


def _client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def upload_to_r2(key: str, body: bytes, content_type: str = "application/octet-stream") -> str:
    bucket = os.environ["R2_BUCKET"]
    client = _client()
    client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)
    return f"{os.environ['R2_ENDPOINT']}/{bucket}/{key}"


def download_from_r2(key: str) -> bytes:
    bucket = os.environ["R2_BUCKET"]
    client = _client()
    obj = client.get_object(Bucket=bucket, Key=key)
    return obj["Body"].read()
