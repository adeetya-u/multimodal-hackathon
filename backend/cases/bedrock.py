from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

_logger = logging.getLogger(__name__)

_client: Any = None

# Fast default for landing demo — override with INTRO_BEDROCK_MODEL.
INTRO_DEFAULT_MODEL = "us.amazon.nova-lite-v1:0"

_AUTH_ERROR_CODES = frozenset(
    {
        "AccessDeniedException",
        "UnauthorizedException",
        "UnrecognizedClientException",
        "InvalidSignatureException",
        "ExpiredTokenException",
    }
)
_THROTTLE_ERROR_CODES = frozenset(
    {
        "ThrottlingException",
        "ServiceUnavailableException",
        "ModelTimeoutException",
        "ModelNotReadyException",
        "InternalServerException",
    }
)


class BedrockFailureKind(str, Enum):
    AUTH = "auth"
    THROTTLE = "throttle"
    OTHER = "other"


@dataclass(frozen=True)
class BedrockFailure:
    kind: BedrockFailureKind
    code: str
    message: str
    retriable: bool


def configure_bedrock_env() -> None:
    key = (
        os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "").strip()
        or os.environ.get("BEDROCK_API_KEY", "").strip()
    )
    if key:
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = key
    os.environ.setdefault("AWS_DEFAULT_REGION", os.environ.get("BEDROCK_REGION", "us-east-1"))


def bedrock_region() -> str:
    return os.environ.get("AWS_DEFAULT_REGION", os.environ.get("BEDROCK_REGION", "us-east-1"))


def _runtime_client():
    global _client
    if _client is None:
        import boto3

        configure_bedrock_env()
        _client = boto3.client("bedrock-runtime", region_name=bedrock_region())
    return _client


def classify_bedrock_error(exc: Exception) -> BedrockFailure:
    code = type(exc).__name__
    message = str(exc)
    try:
        from botocore.exceptions import ClientError

        if isinstance(exc, ClientError):
            err = exc.response.get("Error", {})
            code = str(err.get("Code") or code)
            message = str(err.get("Message") or message)
    except ImportError:
        pass

    if code in _AUTH_ERROR_CODES:
        return BedrockFailure(kind=BedrockFailureKind.AUTH, code=code, message=message, retriable=False)
    if code in _THROTTLE_ERROR_CODES:
        return BedrockFailure(kind=BedrockFailureKind.THROTTLE, code=code, message=message, retriable=True)
    return BedrockFailure(kind=BedrockFailureKind.OTHER, code=code, message=message, retriable=False)


def warm_bedrock_client() -> None:
    """Eager-init boto3 client so first demo question avoids cold-start latency."""
    try:
        _runtime_client()
    except Exception as exc:
        failure = classify_bedrock_error(exc)
        log = _logger.error if failure.kind == BedrockFailureKind.AUTH else _logger.warning
        log("Bedrock warm-up failed (%s/%s): %s", failure.kind.value, failure.code, failure.message)


def converse_text(
    prompt: str,
    *,
    model: str | None = None,
    max_tokens: int = 800,
    temperature: float = 0.2,
) -> str | None:
    response = converse(
        [{"role": "user", "content": [{"text": prompt}]}],
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if not response:
        return None
    return extract_message_text(response.get("output", {}).get("message", {}))


def converse_intro(text: str, *, history: list[tuple[str, str]] | None = None) -> str | None:
    """Minimal-latency Bedrock call for landing demo."""
    from .workers import sanitize_spoken_output

    model = os.environ.get("INTRO_BEDROCK_MODEL", INTRO_DEFAULT_MODEL)
    messages: list[dict] = [
        {
            "role": "user",
            "content": [
                {
                    "text": (
                        "You are Scalpel, a knee orthopedics educator on a public demo.\n"
                        "Reply in ONE short spoken sentence (about 22 words max). "
                        "A second sentence only if essential. Plain speech for TTS — no preamble or lists.\n\n"
                        f"Question: {text}"
                    )
                }
            ],
        }
    ]
    for role, msg in (history or [])[-2:]:
        tag = "assistant" if role == "agent" else "user"
        messages.insert(
            -1,
            {"role": tag, "content": [{"text": msg[:120]}]},
        )
    response = converse(messages, model=model, max_tokens=80, temperature=0.1)
    if not response:
        return None
    spoken = extract_message_text(response.get("output", {}).get("message", {}))
    cleaned = sanitize_spoken_output(spoken)
    return cleaned or None


def converse(
    messages: list[dict],
    *,
    model: str | None = None,
    max_tokens: int = 800,
    temperature: float = 0.2,
    tool_config: dict | None = None,
) -> dict | None:
    model_id = model or os.environ.get("BEDROCK_LLM_MODEL", "us.amazon.nova-2-lite-v1:0")
    try:
        client = _runtime_client()
        kwargs: dict = {
            "modelId": model_id,
            "messages": messages,
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
        }
        if tool_config:
            kwargs["toolConfig"] = tool_config
        return client.converse(**kwargs)
    except Exception as exc:
        failure = classify_bedrock_error(exc)
        if failure.kind == BedrockFailureKind.AUTH:
            _logger.error(
                "Bedrock auth failed (model=%s, code=%s): %s",
                model_id,
                failure.code,
                failure.message,
            )
        elif failure.kind == BedrockFailureKind.THROTTLE:
            _logger.warning(
                "Bedrock throttled (model=%s, code=%s): %s",
                model_id,
                failure.code,
                failure.message,
            )
        else:
            _logger.error(
                "Bedrock converse failed (model=%s, code=%s): %s",
                model_id,
                failure.code,
                failure.message,
            )
        return None


def extract_message_text(message: dict) -> str:
    parts: list[str] = []
    for block in message.get("content", []):
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    return "\n".join(parts).strip()
