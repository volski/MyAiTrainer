"""Config and options flow for AI Trainer."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import selector

from .const import (
    CONF_ALLOW_GROUPS,
    CONF_ALLOWED_NUMBERS,
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_COACH_NAME,
    CONF_DAILY_TIME,
    CONF_ENABLE_DAILY,
    CONF_ENABLE_WATER,
    CONF_ENABLE_WORKOUT,
    CONF_MAX_TOKENS,
    CONF_MAX_USERS,
    CONF_MIN_AI_INTERVAL,
    CONF_MODEL,
    CONF_PROVIDER,
    CONF_SYSTEM_PROMPT_EXTRA,
    CONF_TEMPERATURE,
    CONF_WATER_TIMES,
    CONF_WHATSAPP_ACCOUNT,
    CONF_WHATSAPP_SERVICE,
    CONF_WORKOUT_TIME,
    DEFAULT_DAILY_TIME,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MAX_USERS,
    DEFAULT_MIN_AI_INTERVAL,
    DEFAULT_PROVIDER,
    DEFAULT_TEMPERATURE,
    DEFAULT_WATER_TIMES,
    DEFAULT_WORKOUT_TIME,
    DOMAIN,
    PROVIDERS,
    SERVICE_SEND_MESSAGE,
    TIME_PATTERN,
    WHATSAPP_DOMAIN,
    merged_settings,
)
from .core.models import normalize_phone
from .whatsapp import whatsapp_accounts

_SERVICE_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


def _provider_selector() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                {"value": key, "label": value["label"]}
                for key, value in PROVIDERS.items()
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _account_selector(hass) -> selector.SelectSelector:
    options = [{"value": "", "label": "Default / only account"}]
    for account in whatsapp_accounts(hass):
        label = account.get("title") or account.get("entry_id")
        if account.get("number"):
            label = f"{label} ({account['number']})"
        options.append({"value": account.get("entry_id"), "label": label})
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _text(
    multiline: bool = False,
    password: bool = False,
) -> selector.TextSelector:
    return selector.TextSelector(
        selector.TextSelectorConfig(
            multiline=multiline,
            type=(
                selector.TextSelectorType.PASSWORD
                if password
                else selector.TextSelectorType.TEXT
            ),
        )
    )


def _number(low: float, high: float, step: float = 1) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=low,
            max=high,
            step=step,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _parse_times(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        raw = [str(part).strip() for part in value]
    else:
        raise ValueError("invalid_times")
    result: list[str] = []
    for item in raw:
        if not item:
            continue
        if not TIME_PATTERN.match(item):
            raise ValueError("invalid_times")
        if item not in result:
            result.append(item)
    return sorted(result)


class AITrainerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Initial setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            daily_time = str(user_input.get(CONF_DAILY_TIME) or "").strip()
            if not TIME_PATTERN.match(daily_time):
                errors["base"] = "invalid_time"
            else:
                provider = str(user_input.get(CONF_PROVIDER) or DEFAULT_PROVIDER)
                if provider not in PROVIDERS:
                    errors["base"] = "invalid_provider"
                else:
                    self._check_whatsapp()
                    return self.async_create_entry(
                        title="AI Trainer",
                        data={
                            CONF_PROVIDER: provider,
                            CONF_API_KEY: str(user_input.get(CONF_API_KEY) or "").strip(),
                            CONF_MODEL: str(user_input.get(CONF_MODEL) or "").strip(),
                            CONF_WHATSAPP_ACCOUNT: str(
                                user_input.get(CONF_WHATSAPP_ACCOUNT) or ""
                            ).strip(),
                            CONF_DAILY_TIME: daily_time,
                        },
                    )

        schema = vol.Schema(
            {
                vol.Required(CONF_PROVIDER, default=DEFAULT_PROVIDER): _provider_selector(),
                vol.Optional(CONF_API_KEY, default=""): _text(password=True),
                vol.Optional(CONF_MODEL, default=""): _text(),
                vol.Optional(CONF_WHATSAPP_ACCOUNT, default=""): _account_selector(
                    self.hass
                ),
                vol.Optional(CONF_DAILY_TIME, default=DEFAULT_DAILY_TIME): _text(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    def _check_whatsapp(self) -> None:
        if not self.hass.services.has_service(WHATSAPP_DOMAIN, SERVICE_SEND_MESSAGE):
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                "whatsapp_missing",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="whatsapp_missing",
            )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return AITrainerOptionsFlow()


class AITrainerOptionsFlow(config_entries.OptionsFlow):
    """Edit all runtime settings from the UI."""

    def __init__(self) -> None:
        self._draft: dict[str, Any] = {}
        self._loaded = False

    def _ensure_draft(self) -> None:
        if not self._loaded:
            self._draft = merged_settings(
                self.config_entry.data, self.config_entry.options
            )
            self._loaded = True

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        self._ensure_draft()
        if user_input is not None:
            step = str(user_input.get("next_step_id") or "")
            handler = getattr(self, f"async_step_{step}", None)
            if handler is not None:
                return await handler()
        return self.async_show_menu(
            step_id="init",
            menu_options=["ai", "whatsapp", "schedule", "limits", "prompt", "done"],
        )

    # ------------------------------------------------------------------
    # AI
    # ------------------------------------------------------------------
    async def async_step_ai(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        self._ensure_draft()
        errors: dict[str, str] = {}
        if user_input is not None:
            provider = str(user_input.get(CONF_PROVIDER) or DEFAULT_PROVIDER)
            if provider not in PROVIDERS:
                errors["base"] = "invalid_provider"
            else:
                self._draft[CONF_PROVIDER] = provider
                self._draft[CONF_MODEL] = str(user_input.get(CONF_MODEL) or "").strip()
                self._draft[CONF_BASE_URL] = str(
                    user_input.get(CONF_BASE_URL) or ""
                ).strip()
                self._draft[CONF_TEMPERATURE] = round(
                    float(user_input.get(CONF_TEMPERATURE) or DEFAULT_TEMPERATURE), 2
                )
                self._draft[CONF_MAX_TOKENS] = int(
                    user_input.get(CONF_MAX_TOKENS) or DEFAULT_MAX_TOKENS
                )
                if str(user_input.get(CONF_API_KEY) or "").strip():
                    self._draft[CONF_API_KEY] = str(user_input[CONF_API_KEY]).strip()
                if user_input.get("clear_api_key"):
                    self._draft[CONF_API_KEY] = ""
                return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PROVIDER, default=self._draft.get(CONF_PROVIDER, DEFAULT_PROVIDER)
                ): _provider_selector(),
                vol.Optional(CONF_MODEL, default=self._draft.get(CONF_MODEL, "")): _text(),
                vol.Optional(CONF_API_KEY, default=""): _text(password=True),
                vol.Optional("clear_api_key", default=False): selector.BooleanSelector(),
                vol.Optional(
                    CONF_BASE_URL, default=self._draft.get(CONF_BASE_URL, "")
                ): _text(),
                vol.Optional(
                    CONF_TEMPERATURE,
                    default=self._draft.get(CONF_TEMPERATURE, DEFAULT_TEMPERATURE),
                ): _number(0, 2, 0.1),
                vol.Optional(
                    CONF_MAX_TOKENS,
                    default=self._draft.get(CONF_MAX_TOKENS, DEFAULT_MAX_TOKENS),
                ): _number(64, 4000, 1),
            }
        )
        return self.async_show_form(step_id="ai", data_schema=schema, errors=errors)

    # ------------------------------------------------------------------
    # WhatsApp
    # ------------------------------------------------------------------
    async def async_step_whatsapp(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        self._ensure_draft()
        errors: dict[str, str] = {}
        if user_input is not None:
            service = str(user_input.get(CONF_WHATSAPP_SERVICE) or "").strip()
            if not _SERVICE_PATTERN.match(service):
                errors["base"] = "invalid_service"
            else:
                numbers_raw = str(user_input.get(CONF_ALLOWED_NUMBERS) or "")
                numbers: list[str] = []
                for part in numbers_raw.replace("\n", ",").split(","):
                    phone = normalize_phone(part)
                    if phone and phone not in numbers:
                        numbers.append(phone)
                self._draft[CONF_WHATSAPP_SERVICE] = service
                self._draft[CONF_WHATSAPP_ACCOUNT] = str(
                    user_input.get(CONF_WHATSAPP_ACCOUNT) or ""
                ).strip()
                self._draft[CONF_ALLOW_GROUPS] = bool(
                    user_input.get(CONF_ALLOW_GROUPS, False)
                )
                self._draft[CONF_ALLOWED_NUMBERS] = numbers
                return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_WHATSAPP_SERVICE,
                    default=self._draft.get(
                        CONF_WHATSAPP_SERVICE, "whatsapp.send_message"
                    ),
                ): _text(),
                vol.Optional(
                    CONF_WHATSAPP_ACCOUNT,
                    default=self._draft.get(CONF_WHATSAPP_ACCOUNT, ""),
                ): _account_selector(self.hass),
                vol.Optional(
                    CONF_ALLOW_GROUPS, default=bool(self._draft.get(CONF_ALLOW_GROUPS, False))
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_ALLOWED_NUMBERS,
                    default=", ".join(self._draft.get(CONF_ALLOWED_NUMBERS, [])),
                ): _text(),
            }
        )
        return self.async_show_form(
            step_id="whatsapp", data_schema=schema, errors=errors
        )

    # ------------------------------------------------------------------
    # Schedule
    # ------------------------------------------------------------------
    async def async_step_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        self._ensure_draft()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                daily_time = str(user_input.get(CONF_DAILY_TIME) or "").strip()
                workout_time = str(user_input.get(CONF_WORKOUT_TIME) or "").strip()
                if not TIME_PATTERN.match(daily_time) or not TIME_PATTERN.match(
                    workout_time
                ):
                    raise ValueError("invalid_time")
                water_times = _parse_times(user_input.get(CONF_WATER_TIMES))
            except (TypeError, ValueError):
                errors["base"] = "invalid_times"
            else:
                self._draft[CONF_ENABLE_DAILY] = bool(
                    user_input.get(CONF_ENABLE_DAILY, True)
                )
                self._draft[CONF_ENABLE_WATER] = bool(
                    user_input.get(CONF_ENABLE_WATER, True)
                )
                self._draft[CONF_ENABLE_WORKOUT] = bool(
                    user_input.get(CONF_ENABLE_WORKOUT, True)
                )
                self._draft[CONF_DAILY_TIME] = daily_time
                self._draft[CONF_WORKOUT_TIME] = workout_time
                self._draft[CONF_WATER_TIMES] = water_times
                return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ENABLE_DAILY, default=bool(self._draft.get(CONF_ENABLE_DAILY, True))
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_DAILY_TIME, default=self._draft.get(CONF_DAILY_TIME, DEFAULT_DAILY_TIME)
                ): _text(),
                vol.Optional(
                    CONF_ENABLE_WATER, default=bool(self._draft.get(CONF_ENABLE_WATER, True))
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_WATER_TIMES,
                    default=", ".join(
                        self._draft.get(CONF_WATER_TIMES, DEFAULT_WATER_TIMES)
                    ),
                ): _text(),
                vol.Optional(
                    CONF_ENABLE_WORKOUT,
                    default=bool(self._draft.get(CONF_ENABLE_WORKOUT, True)),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_WORKOUT_TIME,
                    default=self._draft.get(CONF_WORKOUT_TIME, DEFAULT_WORKOUT_TIME),
                ): _text(),
            }
        )
        return self.async_show_form(
            step_id="schedule", data_schema=schema, errors=errors
        )

    # ------------------------------------------------------------------
    # Limits
    # ------------------------------------------------------------------
    async def async_step_limits(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        self._ensure_draft()
        if user_input is not None:
            self._draft[CONF_MAX_USERS] = int(
                user_input.get(CONF_MAX_USERS) or DEFAULT_MAX_USERS
            )
            self._draft[CONF_MIN_AI_INTERVAL] = round(
                float(
                    user_input.get(CONF_MIN_AI_INTERVAL) or DEFAULT_MIN_AI_INTERVAL
                ),
                1,
            )
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_MAX_USERS,
                    default=int(self._draft.get(CONF_MAX_USERS, DEFAULT_MAX_USERS)),
                ): _number(1, 500),
                vol.Optional(
                    CONF_MIN_AI_INTERVAL,
                    default=float(
                        self._draft.get(CONF_MIN_AI_INTERVAL, DEFAULT_MIN_AI_INTERVAL)
                    ),
                ): _number(0, 30, 0.5),
            }
        )
        return self.async_show_form(step_id="limits", data_schema=schema)

    # ------------------------------------------------------------------
    # Persona
    # ------------------------------------------------------------------
    async def async_step_prompt(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        self._ensure_draft()
        if user_input is not None:
            self._draft[CONF_COACH_NAME] = (
                str(user_input.get(CONF_COACH_NAME) or "").strip() or "המאמן"
            )
            self._draft[CONF_SYSTEM_PROMPT_EXTRA] = str(
                user_input.get(CONF_SYSTEM_PROMPT_EXTRA) or ""
            ).strip()
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_COACH_NAME,
                    default=self._draft.get(CONF_COACH_NAME, "המאמן"),
                ): _text(),
                vol.Optional(
                    CONF_SYSTEM_PROMPT_EXTRA,
                    default=self._draft.get(CONF_SYSTEM_PROMPT_EXTRA, ""),
                ): _text(multiline=True),
            }
        )
        return self.async_show_form(step_id="prompt", data_schema=schema)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    async def async_step_done(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        self._ensure_draft()
        return self.async_create_entry(title="", data=self._draft)
