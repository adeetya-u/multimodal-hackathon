"""Fetch secrets from AWS Secrets Manager (optional) or use local .env."""

import json
import os
from functools import lru_cache

import boto3
from botocore.exceptions import ClientError


@lru_cache(maxsize=1)
def get_secrets() -> dict:
    """Return secrets from AWS Secrets Manager when configured, else {}."""
    secret_name = os.getenv("GET_AWS_SECRET_ID")
    if not secret_name:
        return {}

    client = boto3.client(
        service_name="secretsmanager",
        region_name=os.getenv("GET_AWS_REGION"),
        aws_access_key_id=os.getenv("GET_AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("GET_AWS_SECRET_ACCESS_KEY"),
    )
    try:
        response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        raise RuntimeError(f"Unable to fetch secret {secret_name}: {e}") from e

    secret_string = response.get("SecretString")
    if not secret_string:
        raise ValueError("SecretString is empty")

    return json.loads(secret_string)


class _SecretsMap:
    """Dict-like accessor for optional AWS secrets."""

    def get(self, key: str, default=None):
        return get_secrets().get(key, default)


secrets = _SecretsMap()
