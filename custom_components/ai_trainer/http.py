"""Authenticated REST API for the AI Trainer sidebar panel.

Every endpoint requires a Home Assistant admin user.  API keys are write-only:
they can be set through ``POST /config`` but are never returned.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .ai import AIError
from .const import (
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
    DOMAIN,
    PROVIDERS,
    TIME_PATTERN,
    merged_settings,
)
from .core.metrics import GOAL_LABELS
from .core.models import normalize_phone
from .core.onboarding import start_onboarding
from .core.plan import plan_public_view
from .core.text import clean_name
from .runtime import TrainerRuntime, async_get_runtime

_LOGGER = logging.getLogger(__name__)

_VIEWS_KEY = f"{DOMAIN}_views_registered"
_SERVICE_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


def _is_admin(request: web.Request) -> bool:
    user = request.get("hass_user")
    return bool(user and getattr(user, "is_admin", False))


async def _runtime(
    request: web.Request,
) -> tuple[TrainerRuntime | None, web.Response | None]:
    runtime = await async_get_runtime(request.app["hass"])
    if runtime is None:
        return None, web.json_response(
            {"error": "AI Trainer is not configured."}, status=503
        )
    return runtime, None


def _forbidden() -> web.Response:
    return web.json_response({"error": "Admin access required."}, status=403)


async def _body(request: web.Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:  # noqa: BLE001 - empty or invalid body
        return {}
    return data if isinstance(data, dict) else {}


def _as_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "כן"}
    if isinstance(value, (int, float)):
        return bool(value)
    return fallback


def _as_int(value: Any, low: int, high: int) -> int:
    number = int(float(value))
    if number < low or number > high:
        raise ValueError(f"Value must be between {low} and {high}.")
    return number


def _as_float(value: Any, low: float, high: float) -> float:
    number = float(value)
    if number < low or number > high:
        raise ValueError(f"Value must be between {low} and {high}.")
    return number


def _clean_time(value: Any) -> str:
    text = str(value or "").strip()
    if not TIME_PATTERN.match(text):
        raise ValueError("Time must use HH:MM (24h).")
    return text


def _clean_times(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        raw = [str(part).strip() for part in value]
    else:
        raise ValueError("Water times must be a list or comma-separated string.")
    times: list[str] = []
    for item in raw:
        if not item:
            continue
        text = _clean_time(item)
        if text not in times:
            times.append(text)
    return sorted(times)


class ConfigView(HomeAssistantView):
    """Read and update integration settings."""

    url = "/api/ai_trainer/config"
    name = "api:ai_trainer:config"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        if not _is_admin(request):
            return _forbidden()
        runtime, error = await _runtime(request)
        if error:
            return error
        assert runtime is not None
        return self.json(runtime.config_payload())

    async def post(self, request: web.Request) -> web.Response:
        if not _is_admin(request):
            return _forbidden()
        runtime, error = await _runtime(request)
        if error:
            return error
        assert runtime is not None

        body = await _body(request)
        raw = body.get("settings") if isinstance(body.get("settings"), dict) else body
        current = merged_settings(runtime.entry.data, runtime.entry.options)
        updates: dict[str, Any] = {}
        try:
            if CONF_PROVIDER in raw:
                provider = str(raw[CONF_PROVIDER])
                if provider not in PROVIDERS:
                    raise ValueError("Unknown AI provider.")
                updates[CONF_PROVIDER] = provider
            if CONF_MODEL in raw:
                updates[CONF_MODEL] = str(raw[CONF_MODEL] or "").strip()[:120]
            if CONF_BASE_URL in raw:
                updates[CONF_BASE_URL] = str(raw[CONF_BASE_URL] or "").strip()[:300]
            if "api_key" in raw and str(raw.get("api_key") or "").strip():
                updates[CONF_API_KEY] = str(raw["api_key"]).strip()
            if _as_bool(raw.get("clear_api_key"), False):
                updates[CONF_API_KEY] = ""
            if CONF_TEMPERATURE in raw:
                updates[CONF_TEMPERATURE] = round(
                    _as_float(raw[CONF_TEMPERATURE], 0.0, 2.0), 2
                )
            if CONF_MAX_TOKENS in raw:
                updates[CONF_MAX_TOKENS] = _as_int(raw[CONF_MAX_TOKENS], 64, 4000)
            if CONF_WHATSAPP_ACCOUNT in raw:
                updates[CONF_WHATSAPP_ACCOUNT] = str(
                    raw[CONF_WHATSAPP_ACCOUNT] or ""
                ).strip()[:120]
            if CONF_WHATSAPP_SERVICE in raw:
                service = str(raw[CONF_WHATSAPP_SERVICE] or "").strip()
                if not _SERVICE_PATTERN.match(service):
                    raise ValueError("WhatsApp service must look like domain.service.")
                updates[CONF_WHATSAPP_SERVICE] = service
            if CONF_DAILY_TIME in raw:
                updates[CONF_DAILY_TIME] = _clean_time(raw[CONF_DAILY_TIME])
            if CONF_WORKOUT_TIME in raw:
                updates[CONF_WORKOUT_TIME] = _clean_time(raw[CONF_WORKOUT_TIME])
            if CONF_WATER_TIMES in raw:
                updates[CONF_WATER_TIMES] = _clean_times(raw[CONF_WATER_TIMES])
            for key in (CONF_ENABLE_DAILY, CONF_ENABLE_WATER, CONF_ENABLE_WORKOUT):
                if key in raw:
                    updates[key] = _as_bool(raw[key], current.get(key, True))
            if CONF_ALLOWED_NUMBERS in raw:
                value = raw[CONF_ALLOWED_NUMBERS]
                if isinstance(value, str):
                    value = [part for part in value.replace("\n", ",").split(",")]
                numbers: list[str] = []
                for item in value or []:
                    phone = normalize_phone(item)
                    if phone and len(phone) >= 6 and phone not in numbers:
                        numbers.append(phone)
                updates[CONF_ALLOWED_NUMBERS] = numbers
            if CONF_MAX_USERS in raw:
                updates[CONF_MAX_USERS] = _as_int(raw[CONF_MAX_USERS], 1, 500)
            if CONF_MIN_AI_INTERVAL in raw:
                updates[CONF_MIN_AI_INTERVAL] = round(
                    _as_float(raw[CONF_MIN_AI_INTERVAL], 0.0, 30.0), 1
                )
            if CONF_COACH_NAME in raw:
                updates[CONF_COACH_NAME] = (
                    str(raw[CONF_COACH_NAME] or "").strip()[:40] or "המאמן"
                )
            if CONF_SYSTEM_PROMPT_EXTRA in raw:
                updates[CONF_SYSTEM_PROMPT_EXTRA] = str(
                    raw[CONF_SYSTEM_PROMPT_EXTRA] or ""
                ).strip()[:2000]
        except (TypeError, ValueError) as err:
            return self.json({"error": f"Invalid settings: {err}"}, status_code=400)

        new_options = {**current, **updates}
        request.app["hass"].config_entries.async_update_entry(
            runtime.entry, options=new_options
        )
        await runtime.async_apply_settings()
        return self.json(
            {
                "ok": True,
                "settings": runtime.public_settings(),
                "stats": runtime.stats(),
            }
        )


class UsersView(HomeAssistantView):
    """List and create users."""

    url = "/api/ai_trainer/users"
    name = "api:ai_trainer:users"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        if not _is_admin(request):
            return _forbidden()
        runtime, error = await _runtime(request)
        if error:
            return error
        assert runtime is not None
        users = sorted(
            runtime.store.users.values(),
            key=lambda item: str(item.get("created_at") or ""),
            reverse=True,
        )
        return self.json({"users": [runtime.user_summary(user) for user in users]})

    async def post(self, request: web.Request) -> web.Response:
        if not _is_admin(request):
            return _forbidden()
        runtime, error = await _runtime(request)
        if error:
            return error
        assert runtime is not None

        body = await _body(request)
        phone = normalize_phone(body.get("phone"))
        if len(phone) < 6:
            return self.json(
                {"error": "Phone number is required (with country code)."},
                status_code=400,
            )
        if runtime.store.get_user(phone):
            return self.json({"error": "User already exists."}, status_code=409)
        max_users = int(runtime.settings.get(CONF_MAX_USERS) or 25)
        if len(runtime.store.users) >= max_users:
            return self.json(
                {"error": f"User limit reached ({max_users})."}, status_code=409
            )

        name = clean_name(body.get("name"), fallback="")
        user = runtime.store.create_user(phone, f"{phone}@s.whatsapp.net", name)
        send_greeting = _as_bool(body.get("send_greeting"), True)
        runtime.logs.info("user_created", "משתמש נוצר מהלוח", phone)
        if send_greeting:
            async with runtime.lock_for(str(user["id"])):
                reply = start_onboarding(
                    user, str(runtime.settings.get(CONF_COACH_NAME) or "המאמן")
                )
                await runtime.agent.async_send(
                    user, reply, str(user.get("jid") or "")
                )
        return self.json({"ok": True, "user": runtime.user_detail(user)}, status_code=201)


class UserView(HomeAssistantView):
    """Read, update or delete one user."""

    url = "/api/ai_trainer/users/{user_id}"
    name = "api:ai_trainer:user"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        try:
            if not _is_admin(request):
                return _forbidden()
            runtime, error = await _runtime(request)
            if error:
                return error
            assert runtime is not None
            user = runtime.find_user(request.match_info["user_id"])
            if user is None:
                return self.json({"error": "User not found."}, status_code=404)
            try:
                detail = runtime.user_detail(user)
                return self.json({"user": detail})
            except Exception as err:  # noqa: BLE001 - surface the real cause to the caller
                _LOGGER.exception("AI Trainer user_detail failed")
                try:
                    return self.json(
                        {"error": f"{type(err).__name__}: {err}"}, status_code=500
                    )
                except Exception:  # noqa: BLE001
                    return web.Response(
                        text=f"{type(err).__name__}: {err}", status=500
                    )
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("AI Trainer UserView.get crashed")
            try:
                return web.json_response(
                    {"error": f"{type(err).__name__}: {err}"}, status=500
                )
            except Exception:  # noqa: BLE001
                return web.Response(text=f"{type(err).__name__}: {err}", status=500)

    async def patch(self, request: web.Request) -> web.Response:
        if not _is_admin(request):
            return _forbidden()
        runtime, error = await _runtime(request)
        if error:
            return error
        assert runtime is not None
        user = runtime.find_user(request.match_info["user_id"])
        if user is None:
            return self.json({"error": "User not found."}, status_code=404)

        body = await _body(request)
        profile = user.setdefault("profile", {})
        profile_updates = body.get("profile") if isinstance(body.get("profile"), dict) else body
        try:
            if "name" in body:
                user["name"] = clean_name(body["name"], fallback=str(user.get("name") or ""))
            if "notes" in body:
                user["notes"] = str(body["notes"] or "")[:1000]
            if "status" in body:
                status = str(body["status"])
                if status not in {"active", "paused"}:
                    raise ValueError("Status must be active or paused.")
                user["status"] = status
            if "goal" in profile_updates:
                goal = str(profile_updates["goal"] or "")
                if goal and goal not in GOAL_LABELS:
                    raise ValueError("Unknown goal.")
                profile["goal"] = goal or None
            if "goal_text" in profile_updates:
                profile["goal_text"] = str(profile_updates["goal_text"] or "")[:160]
            if "weight_kg" in profile_updates:
                value = profile_updates["weight_kg"]
                if value in (None, ""):
                    profile["weight_kg"] = None
                else:
                    profile["weight_kg"] = round(_as_float(value, 25, 350), 1)
                    if not profile.get("start_weight_kg"):
                        profile["start_weight_kg"] = profile["weight_kg"]
            if "height_cm" in profile_updates:
                value = profile_updates["height_cm"]
                if value in (None, ""):
                    profile["height_cm"] = None
                else:
                    profile["height_cm"] = _as_int(value, 100, 250)
            if "age" in profile_updates:
                profile["age"] = _as_int(profile_updates["age"], 12, 100)
            if "sex" in profile_updates:
                sex = str(profile_updates["sex"])
                if sex not in {"male", "female", "unspecified"}:
                    raise ValueError("Sex must be male, female or unspecified.")
                profile["sex"] = sex
            if "activity_level" in profile_updates:
                level = str(profile_updates["activity_level"])
                if level not in {"low", "moderate", "high"}:
                    raise ValueError("Activity level must be low, moderate or high.")
                profile["activity_level"] = level
            if "restrictions" in profile_updates:
                profile["restrictions"] = str(profile_updates["restrictions"] or "")[:300]
            if "target_weight_kg" in profile_updates:
                value = profile_updates["target_weight_kg"]
                profile["target_weight_kg"] = (
                    None if value in (None, "") else round(_as_float(value, 25, 350), 1)
                )
        except (TypeError, ValueError) as err:
            return self.json({"error": f"Invalid profile: {err}"}, status_code=400)

        runtime.store.touch(user)
        return self.json({"ok": True, "user": runtime.user_detail(user)})

    async def delete(self, request: web.Request) -> web.Response:
        if not _is_admin(request):
            return _forbidden()
        runtime, error = await _runtime(request)
        if error:
            return error
        assert runtime is not None
        user = runtime.find_user(request.match_info["user_id"])
        if user is None:
            return self.json({"error": "User not found."}, status_code=404)
        runtime.store.delete_user(user.get("id"))
        runtime.logs.info("user_deleted", "משתמש נמחק", str(user.get("id")))
        return self.json({"ok": True})


class UserResetView(HomeAssistantView):
    """Reset one user's profile and restart onboarding."""

    url = "/api/ai_trainer/users/{user_id}/reset"
    name = "api:ai_trainer:user_reset"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        if not _is_admin(request):
            return _forbidden()
        runtime, error = await _runtime(request)
        if error:
            return error
        assert runtime is not None
        user = runtime.find_user(request.match_info["user_id"])
        if user is None:
            return self.json({"error": "User not found."}, status_code=404)

        body = await _body(request)
        send = _as_bool(body.get("send"), True)
        fresh = await runtime.agent.async_reset_user_for(
            str(user.get("phone") or user.get("id")), deliver=send
        )
        if fresh is None:
            return self.json({"error": "User not found."}, status_code=404)
        return self.json(
            {"ok": True, "sent": send, "user": runtime.user_detail(fresh)}
        )


class UserPlanView(HomeAssistantView):
    """Generate and optionally send today's plan."""

    url = "/api/ai_trainer/users/{user_id}/plan"
    name = "api:ai_trainer:user_plan"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        if not _is_admin(request):
            return _forbidden()
        runtime, error = await _runtime(request)
        if error:
            return error
        assert runtime is not None
        user = runtime.find_user(request.match_info["user_id"])
        if user is None:
            return self.json({"error": "User not found."}, status_code=404)
        profile = user.get("profile") or {}
        if not profile.get("weight_kg") or not profile.get("height_cm"):
            return self.json(
                {"error": "User profile is incomplete (weight and height required)."},
                status_code=400,
            )

        body = await _body(request)
        force = _as_bool(body.get("force"), False)
        send = _as_bool(body.get("send"), True)
        async with runtime.lock_for(str(user["id"])):
            plan = await runtime.agent.async_build_plan(user, force=force)
            if send:
                await runtime.agent.async_send(
                    user, str(plan.get("text") or ""), str(user.get("jid") or "")
                )
        return self.json(
            {
                "ok": True,
                "sent": send,
                "plan": plan_public_view(plan),
                "text": plan.get("text"),
                "user": runtime.user_detail(user),
            }
        )


class UserMessageView(HomeAssistantView):
    """Send a manual message to one user."""

    url = "/api/ai_trainer/users/{user_id}/message"
    name = "api:ai_trainer:user_message"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        if not _is_admin(request):
            return _forbidden()
        runtime, error = await _runtime(request)
        if error:
            return error
        assert runtime is not None
        user = runtime.find_user(request.match_info["user_id"])
        if user is None:
            return self.json({"error": "User not found."}, status_code=404)

        body = await _body(request)
        message = str(body.get("message") or "").strip()
        if not message:
            return self.json({"error": "Message is empty."}, status_code=400)
        if len(message) > 4000:
            return self.json({"error": "Message is too long."}, status_code=400)

        sent = await runtime.agent.async_send(
            user, message, str(user.get("jid") or "")
        )
        return self.json({"ok": sent, "user": runtime.user_detail(user)})


class UserSimulateView(HomeAssistantView):
    """Inject a test message as if the user wrote it."""

    url = "/api/ai_trainer/users/{user_id}/simulate"
    name = "api:ai_trainer:user_simulate"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        if not _is_admin(request):
            return _forbidden()
        runtime, error = await _runtime(request)
        if error:
            return error
        assert runtime is not None
        user = runtime.find_user(request.match_info["user_id"])
        if user is None:
            return self.json({"error": "User not found."}, status_code=404)

        body = await _body(request)
        text = str(body.get("text") or "").strip()
        if not text:
            return self.json({"error": "Text is empty."}, status_code=400)

        await runtime.agent.async_handle_message(
            phone=str(user.get("id")),
            target=str(user.get("jid") or ""),
            name=str(user.get("name") or ""),
            text=text,
            is_group=False,
            message_id=f"panel-{dt_util.now().timestamp()}",
        )
        return self.json({"ok": True, "user": runtime.user_detail(user)})


class TestView(HomeAssistantView):
    """Test AI or WhatsApp connectivity."""

    url = "/api/ai_trainer/test"
    name = "api:ai_trainer:test"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        if not _is_admin(request):
            return _forbidden()
        runtime, error = await _runtime(request)
        if error:
            return error
        assert runtime is not None
        body = await _body(request)
        kind = str(body.get("kind") or "ai")

        if kind == "ai":
            try:
                result = await runtime.async_test_provider()
            except AIError as err:
                return self.json(
                    {"ok": False, "error": str(err)}, status_code=400
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("AI Trainer provider test failed")
                return self.json(
                    {"ok": False, "error": type(err).__name__}, status_code=400
                )
            return self.json(result)

        if kind == "whatsapp":
            phone = normalize_phone(body.get("phone"))
            if len(phone) < 6:
                return self.json(
                    {"ok": False, "error": "Phone number is required."},
                    status_code=400,
                )
            if not runtime.bridge.available:
                return self.json(
                    {"ok": False, "error": "WhatsApp service is not available."},
                    status_code=400,
                )
            result = await runtime.async_test_whatsapp(phone)
            return self.json(result, status_code=200 if result.get("ok") else 400)

        return self.json({"error": "Unknown test kind."}, status_code=400)


class LogsView(HomeAssistantView):
    """Recent integration activity."""

    url = "/api/ai_trainer/logs"
    name = "api:ai_trainer:logs"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        if not _is_admin(request):
            return _forbidden()
        runtime, error = await _runtime(request)
        if error:
            return error
        assert runtime is not None
        try:
            limit = int(request.query.get("limit", 100))
        except ValueError:
            limit = 100
        return self.json({"logs": runtime.logs.as_list(max(1, min(limit, 300)))})


VIEW_CLASSES = (
    ConfigView,
    UsersView,
    UserView,
    UserResetView,
    UserPlanView,
    UserMessageView,
    UserSimulateView,
    TestView,
    LogsView,
)


def async_register_views(hass: HomeAssistant) -> None:
    """Register all REST views once."""
    if hass.data.get(_VIEWS_KEY):
        return
    for view_class in VIEW_CLASSES:
        hass.http.register_view(view_class())
    hass.data[_VIEWS_KEY] = True
