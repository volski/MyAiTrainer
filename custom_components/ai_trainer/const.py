"""Constants for the AI Trainer integration.

The integration keeps all of its configuration in the Home Assistant config
entry.  Values in ``options`` override values in ``data`` so that the options
flow (and the sidebar panel) can change settings without re-adding the
integration.
"""

from __future__ import annotations

import re
from typing import Any, Final

DOMAIN: Final = "ai_trainer"
NAME: Final = "AI Trainer"
VERSION: Final = "1.0.17"

# Frontend
PANEL_URL: Final = "ai-trainer"
PANEL_ELEMENT: Final = "ai-trainer-panel"
PANEL_TITLE: Final = "AI Trainer"
PANEL_ICON: Final = "mdi:robot-happy-outline"
STATIC_URL: Final = "/ai_trainer_static"
PANEL_JS: Final = "ai-trainer-panel.js"

# Events published by FaserF/ha-whatsapp
WHATSAPP_DOMAIN: Final = "whatsapp"
EVENT_MESSAGE_RECEIVED: Final = "whatsapp_message_received"
SERVICE_SEND_MESSAGE: Final = "send_message"

# Config entry keys
CONF_PROVIDER: Final = "provider"
CONF_MODEL: Final = "model"
CONF_API_KEY: Final = "api_key"
CONF_BASE_URL: Final = "base_url"
CONF_TEMPERATURE: Final = "temperature"
CONF_MAX_TOKENS: Final = "max_tokens"

CONF_WHATSAPP_ACCOUNT: Final = "whatsapp_account"
CONF_WHATSAPP_SERVICE: Final = "whatsapp_service"
CONF_ALLOW_GROUPS: Final = "allow_groups"
CONF_ALLOWED_NUMBERS: Final = "allowed_numbers"

CONF_DAILY_TIME: Final = "daily_time"
CONF_WATER_TIMES: Final = "water_times"
CONF_WORKOUT_TIME: Final = "workout_time"
CONF_ENABLE_DAILY: Final = "enable_daily"
CONF_ENABLE_WATER: Final = "enable_water"
CONF_ENABLE_WORKOUT: Final = "enable_workout"

CONF_COACH_NAME: Final = "coach_name"
CONF_SYSTEM_PROMPT_EXTRA: Final = "system_prompt_extra"
CONF_MAX_USERS: Final = "max_users"
CONF_MIN_AI_INTERVAL: Final = "min_ai_interval"

# Defaults
DEFAULT_PROVIDER: Final = "openai"
DEFAULT_TEMPERATURE: Final = 0.7
DEFAULT_MAX_TOKENS: Final = 700
DEFAULT_WHATSAPP_SERVICE: Final = "whatsapp.send_message"
DEFAULT_DAILY_TIME: Final = "08:00"
DEFAULT_WATER_TIMES: Final = ["10:00", "13:00", "16:00", "19:00"]
DEFAULT_WORKOUT_TIME: Final = "18:00"
DEFAULT_COACH_NAME: Final = "המאמן"
DEFAULT_MAX_USERS: Final = 25
DEFAULT_MIN_AI_INTERVAL: Final = 2.0

# Provider catalogue.  ``requires_key`` is a hint for the UI; the backend
# still allows saving an empty key so onboarding works before AI is set up.
PROVIDERS: Final[dict[str, dict[str, Any]]] = {
    "openai": {
        "label": "OpenAI",
        "default_model": "gpt-4o-mini",
        "requires_key": True,
        "supports_base_url": False,
        "kind": "openai",
    },
    "anthropic": {
        "label": "Anthropic (Claude)",
        "default_model": "claude-3-5-haiku-latest",
        "requires_key": True,
        "supports_base_url": False,
        "kind": "anthropic",
    },
    "google": {
        "label": "Google Gemini",
        "default_model": "gemini-2.5-flash",
        "requires_key": True,
        "supports_base_url": False,
        "kind": "google",
    },
    "deepseek": {
        "label": "DeepSeek",
        "default_model": "deepseek-chat",
        "requires_key": True,
        "supports_base_url": True,
        "base_url": "https://api.deepseek.com/v1",
        "kind": "openai",
    },
    "ollama": {
        "label": "Ollama (local)",
        "default_model": "llama3.1:8b",
        "requires_key": False,
        "supports_base_url": True,
        "base_url": "http://homeassistant.local:11434",
        "kind": "ollama",
    },
    "openai_compatible": {
        "label": "OpenAI-compatible",
        "default_model": "",
        "requires_key": False,
        "supports_base_url": True,
        "base_url": "",
        "kind": "openai",
    },
}

DEFAULT_MODELS: Final[dict[str, str]] = {
    key: value["default_model"] for key, value in PROVIDERS.items()
}

TIME_PATTERN: Final = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")

DEFAULT_OPTIONS: Final[dict[str, Any]] = {
    CONF_PROVIDER: DEFAULT_PROVIDER,
    CONF_MODEL: "",
    CONF_API_KEY: "",
    CONF_BASE_URL: "",
    CONF_TEMPERATURE: DEFAULT_TEMPERATURE,
    CONF_MAX_TOKENS: DEFAULT_MAX_TOKENS,
    CONF_WHATSAPP_ACCOUNT: "",
    CONF_WHATSAPP_SERVICE: DEFAULT_WHATSAPP_SERVICE,
    CONF_ALLOW_GROUPS: False,
    CONF_ALLOWED_NUMBERS: [],
    CONF_DAILY_TIME: DEFAULT_DAILY_TIME,
    CONF_WATER_TIMES: list(DEFAULT_WATER_TIMES),
    CONF_WORKOUT_TIME: DEFAULT_WORKOUT_TIME,
    CONF_ENABLE_DAILY: True,
    CONF_ENABLE_WATER: True,
    CONF_ENABLE_WORKOUT: True,
    CONF_COACH_NAME: DEFAULT_COACH_NAME,
    CONF_SYSTEM_PROMPT_EXTRA: "",
    CONF_MAX_USERS: DEFAULT_MAX_USERS,
    CONF_MIN_AI_INTERVAL: DEFAULT_MIN_AI_INTERVAL,
}

# Keys that may be written through the panel / options flow.
EDITABLE_KEYS: Final = tuple(DEFAULT_OPTIONS)

# How many chat messages are kept per user (rendered in the panel).
HISTORY_LIMIT: Final = 40
# How many daily plans are kept per user.
PLAN_HISTORY_LIMIT: Final = 7
# How many log entries are kept in memory.
LOG_LIMIT: Final = 300

WATER_CUP_ML: Final = 250
MAX_WATER_ML: Final = 6000


def merged_settings(
    data: dict[str, Any] | None, options: dict[str, Any] | None
) -> dict[str, Any]:
    """Return configuration merged over defaults (options win over data)."""
    merged = dict(DEFAULT_OPTIONS)
    for source in (data or {}, options or {}):
        for key, value in source.items():
            if key in EDITABLE_KEYS and value is not None:
                merged[key] = value
    merged[CONF_WATER_TIMES] = _clean_times(merged.get(CONF_WATER_TIMES))
    merged[CONF_DAILY_TIME] = _clean_time(merged.get(CONF_DAILY_TIME), DEFAULT_DAILY_TIME)
    merged[CONF_WORKOUT_TIME] = _clean_time(
        merged.get(CONF_WORKOUT_TIME), DEFAULT_WORKOUT_TIME
    )
    return merged


def _clean_time(value: Any, fallback: str) -> str:
    """Return a valid HH:MM string or ``fallback``."""
    text = str(value or "").strip()
    return text if TIME_PATTERN.match(text) else fallback


def _clean_times(value: Any) -> list[str]:
    """Normalise a list of HH:MM strings, dropping invalid entries."""
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, (list, tuple)):
        return list(DEFAULT_WATER_TIMES)
    seen: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if TIME_PATTERN.match(text) and text not in seen:
            seen.append(text)
    return sorted(seen) if seen else []


def provider_meta(provider: str | None) -> dict[str, Any]:
    """Return metadata for a provider, falling back to OpenAI."""
    return PROVIDERS.get(str(provider or ""), PROVIDERS[DEFAULT_PROVIDER])


def default_model_for(provider: str | None) -> str:
    """Return the default model for a provider."""
    return str(provider_meta(provider).get("default_model") or "")
