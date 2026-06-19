"""Unified LLM client — MiniMax / Nebius (OpenAI-compatible) with optional Bedrock fallback."""

from __future__ import annotations

import logging
import os
from typing import Any

_logger = logging.getLogger(__name__)

_openai_client: Any = None
INTRO_DEFAULT_MODEL = "meta-llama/Llama-3.3-70B-Instruct"
MINIMAX_DEFAULT_MODEL = "MiniMax-M2.1"


def llm_provider() -> str:
    return os.environ.get("LLM_PROVIDER", "nebius").strip().lower()


def configure_llm_env() -> None:
    """Warm env for whichever provider is active."""
    if llm_provider() == "bedrock":
        from .bedrock import configure_bedrock_env

        configure_bedrock_env()
        return
    if llm_provider() == "minimax":
        os.environ.setdefault("MINIMAX_BASE_URL", "https://api.minimax.io/v1")
        return
    os.environ.setdefault("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")


def warm_llm_client() -> None:
    configure_llm_env()
    if llm_provider() == "bedrock":
        from .bedrock import warm_bedrock_client

        warm_bedrock_client()
        return
    try:
        _openai_client_instance()
    except Exception as exc:
        _logger.warning("%s LLM warm-up failed: %s", llm_provider(), exc)


def _env_chain(*keys: str) -> str:
    for key in keys:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def resolve_model(role: str = "default") -> str | None:
    """Resolve model id for a pipeline role (logger, answer, summary, intro, intent)."""
    provider = llm_provider()
    if provider == "bedrock":
        role_keys = {
            "logger": ("BEDROCK_LOGGER_MODEL", "BEDROCK_LLM_MODEL"),
            "answer": ("BEDROCK_ANSWER_MODEL", "BEDROCK_LLM_MODEL"),
            "summary": ("BEDROCK_SUMMARY_MODEL", "BEDROCK_LLM_MODEL"),
            "intro": ("INTRO_BEDROCK_MODEL", "BEDROCK_LLM_MODEL"),
            "intent": ("BEDROCK_INTENT_MODEL", "BEDROCK_LOGGER_MODEL", "BEDROCK_LLM_MODEL"),
            "default": ("BEDROCK_LLM_MODEL",),
        }
        return _env_chain(*role_keys.get(role, role_keys["default"])) or None
    if provider == "minimax":
        role_keys = {
            "logger": ("MINIMAX_MODEL_LOGGER", "MINIMAX_LLM_MODEL"),
            "answer": ("MINIMAX_MODEL_ANSWER", "MINIMAX_LLM_MODEL"),
            "summary": ("MINIMAX_MODEL_SUMMARY", "MINIMAX_LLM_MODEL"),
            "intro": ("MINIMAX_MODEL_INTRO", "MINIMAX_LLM_MODEL"),
            "intent": ("MINIMAX_MODEL_LOGGER", "MINIMAX_LLM_MODEL"),
            "checklist": ("MINIMAX_MODEL_LOGGER", "MINIMAX_LLM_MODEL"),
            "default": ("MINIMAX_LLM_MODEL",),
        }
        return _env_chain(*role_keys.get(role, role_keys["default"])) or MINIMAX_DEFAULT_MODEL
    role_keys = {
        "logger": ("NEBIUS_MODEL_LOGGER", "NEBIUS_MODEL_DEFAULT"),
        "answer": ("NEBIUS_MODEL_ANSWER", "NEBIUS_MODEL_DEFAULT"),
        "summary": ("NEBIUS_MODEL_SUMMARY", "NEBIUS_MODEL_DEFAULT"),
        "intro": ("NEBIUS_MODEL_INTRO", "NEBIUS_MODEL_DEFAULT"),
        "intent": ("NEBIUS_MODEL_LOGGER", "NEBIUS_MODEL_DEFAULT"),
        "checklist": ("NEBIUS_MODEL_CHECKLIST", "NEBIUS_MODEL_LOGGER", "NEBIUS_MODEL_DEFAULT"),
        "default": ("NEBIUS_MODEL_DEFAULT", "NEBIUS_MODEL_LOGGER"),
    }
    return _env_chain(*role_keys.get(role, role_keys["default"])) or INTRO_DEFAULT_MODEL


def openai_chat_config() -> tuple[str, str, str]:
    """Return (model, base_url, api_key) for langchain-openai / OpenAI SDK callers."""
    provider = llm_provider()
    if provider == "minimax":
        key = os.environ.get("MINIMAX_API_KEY", "").strip()
        if not key:
            raise ValueError("MINIMAX_API_KEY is not set")
        base = os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.io/v1").strip().rstrip("/")
        return resolve_model("default") or MINIMAX_DEFAULT_MODEL, f"{base}/", key
    key = os.environ.get("NEBIUS_API_KEY", "").strip()
    if not key:
        raise ValueError("NEBIUS_API_KEY is not set")
    base = os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/").strip()
    return resolve_model("default") or INTRO_DEFAULT_MODEL, base, key


def _default_model() -> str:
    return resolve_model("default") or INTRO_DEFAULT_MODEL


def _openai_client_instance():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI

        model, base, key = openai_chat_config()
        del model  # model chosen per request
        _openai_client = OpenAI(base_url=base, api_key=key)
    return _openai_client


def converse_text(
    prompt: str,
    *,
    model: str | None = None,
    max_tokens: int = 800,
    temperature: float = 0.2,
) -> str | None:
    if llm_provider() == "bedrock":
        from .bedrock import converse_text as bedrock_converse_text

        return bedrock_converse_text(
            prompt, model=model, max_tokens=max_tokens, temperature=temperature
        )
    model_id = (model or _default_model()).strip()
    provider = llm_provider()
    try:
        client = _openai_client_instance()
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        choice = response.choices[0] if response.choices else None
        if not choice or not choice.message.content:
            return None
        return choice.message.content.strip()
    except Exception as exc:
        _logger.error("%s converse_text failed (model=%s): %s", provider, model_id, exc)
        return None


def converse_intro(text: str, *, history: list[tuple[str, str]] | None = None) -> str | None:
    if llm_provider() == "bedrock":
        from .bedrock import converse_intro as bedrock_intro

        return bedrock_intro(text, history=history)

    model = resolve_model("intro") or INTRO_DEFAULT_MODEL
    messages: list[dict] = [
        {
            "role": "user",
            "content": [
                {
                    "text": (
                        "You are Scalpel, a knee orthopedics educator on a public demo.\n"
                        "Reply with one or two short spoken sentences for text-to-speech.\n"
                        "Plain speech only — no headings, labels, Q/A prefixes, or refusals.\n\n"
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
    if not spoken:
        return None
    from .workers import sanitize_spoken_output

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
    if llm_provider() == "bedrock":
        from .bedrock import converse as bedrock_converse

        return bedrock_converse(
            messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            tool_config=tool_config,
        )
    model_id = (model or _default_model()).strip()
    provider = llm_provider()
    oai_messages: list[dict[str, str]] = []
    for msg in messages:
        role = str(msg.get("role", "user"))
        content_blocks = msg.get("content") or []
        text_parts: list[str] = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("text"):
                text_parts.append(str(block["text"]))
            elif isinstance(block, str):
                text_parts.append(block)
        if text_parts:
            oai_messages.append({"role": role, "content": "\n".join(text_parts)})
    if not oai_messages:
        return None
    try:
        client = _openai_client_instance()
        kwargs: dict[str, Any] = {
            "model": model_id,
            "messages": oai_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tool_config:
            tools = tool_config.get("tools") or []
            oai_tools = []
            for tool in tools:
                spec = tool.get("toolSpec") or tool
                oai_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": spec.get("name", "tool"),
                            "description": (spec.get("description") or "")[:500],
                            "parameters": spec.get("inputSchema", {}).get("json", {}),
                        },
                    }
                )
            if oai_tools:
                kwargs["tools"] = oai_tools
        response = client.chat.completions.create(**kwargs)
        text = response.choices[0].message.content if response.choices else ""
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": text or ""}],
                }
            }
        }
    except Exception as exc:
        _logger.error("%s converse failed (model=%s): %s", provider, model_id, exc)
        return None


def extract_message_text(message: dict) -> str:
    from .bedrock import extract_message_text as bedrock_extract

    return bedrock_extract(message)


# Back-compat aliases used across the codebase
configure_bedrock_env = configure_llm_env
warm_bedrock_client = warm_llm_client
