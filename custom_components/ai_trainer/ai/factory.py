"""Provider factory."""

from __future__ import annotations

from typing import Any

import aiohttp

from ..const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_MAX_TOKENS,
    CONF_MODEL,
    CONF_PROVIDER,
    CONF_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_PROVIDER,
    DEFAULT_TEMPERATURE,
    PROVIDERS,
    provider_meta,
)
from .anthropic_provider import AnthropicProvider
from .base import AIError, AIProvider
from .google_provider import GoogleProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider, parse_json_response

__all__ = [
    "AIError",
    "AIProvider",
    "create_provider",
    "parse_json_response",
    "provider_catalogue",
]


def _number(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def create_provider(
    settings: dict[str, Any],
    session: aiohttp.ClientSession,
) -> AIProvider:
    """Create the provider described by the merged settings."""
    provider_id = str(settings.get(CONF_PROVIDER) or DEFAULT_PROVIDER)
    if provider_id not in PROVIDERS:
        provider_id = DEFAULT_PROVIDER
    meta = provider_meta(provider_id)
    kind = str(meta.get("kind") or "openai")

    model = str(settings.get(CONF_MODEL) or meta.get("default_model") or "").strip()
    # Migrate unavailable/deprecated Google model names to the current stable default.
    if provider_id == "google" and model in {
        "gemini-2.5-flash",
        "models/gemini-2.5-flash",
        "gemini-3.8-flash",
        "models/gemini-3.8-flash",
    }:
        model = str(meta.get("default_model") or "gemini-2.0-flash").strip()
    base_url = str(settings.get(CONF_BASE_URL) or meta.get("base_url") or "").strip()
    api_key = str(settings.get(CONF_API_KEY) or "").strip()
    temperature = max(
        0.0,
        min(2.0, _number(settings.get(CONF_TEMPERATURE), DEFAULT_TEMPERATURE)),
    )
    max_tokens = int(
        max(64, min(4000, _number(settings.get(CONF_MAX_TOKENS), DEFAULT_MAX_TOKENS)))
    )

    common: dict[str, Any] = {
        "session": session,
        "api_key": api_key,
        "model": model,
        "base_url": base_url,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "requires_key": bool(meta.get("requires_key", True)),
    }

    if kind == "anthropic":
        return AnthropicProvider(**common)
    if kind == "google":
        return GoogleProvider(**common)
    if kind == "ollama":
        return OllamaProvider(**common)
    return OpenAIProvider(**common)


def provider_catalogue() -> list[dict[str, Any]]:
    """Return provider metadata for the panel."""
    return [
        {
            "id": key,
            "label": value.get("label", key),
            "default_model": value.get("default_model", ""),
            "requires_key": bool(value.get("requires_key", True)),
            "supports_base_url": bool(value.get("supports_base_url", False)),
            "base_url": value.get("base_url", ""),
        }
        for key, value in PROVIDERS.items()
    ]
