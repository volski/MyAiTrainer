"""User and profile data structures.

Users are plain dictionaries so they serialise directly to the Home
Assistant storage file and to the panel REST API.
"""

from __future__ import annotations

import re
from typing import Any


def normalize_phone(value: Any) -> str:
    """Return a phone number containing digits only.

    WhatsApp JIDs such as ``972501234567@s.whatsapp.net`` are reduced to
    ``972501234567``.  A leading ``00`` international prefix is normalised
    to the bare country code.
    """
    text = str(value or "").strip()
    if "@" in text:
        text = text.split("@", 1)[0]
    digits = re.sub(r"\D", "", text)
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def new_profile() -> dict[str, Any]:
    """Return an empty profile."""
    return {
        "goal": None,
        "goal_text": "",
        "weight_kg": None,
        "height_cm": None,
        "start_weight_kg": None,
        "target_weight_kg": None,
        "age": 30,
        "sex": "unspecified",
        "activity_level": "moderate",
        "restrictions": "",
    }


def new_stats(today: str) -> dict[str, Any]:
    """Return the initial statistics block for a user."""
    return {
        "water_ml_today": 0,
        "water_date": today,
        "messages_today": 0,
        "messages_date": today,
        "checkin_dates": [],
        "workouts": [],
        "total_workouts": 0,
        "last_checkin": None,
        "last_ai_at": None,
        "calories_today": 0,
        "calories_date": today,
        "drinks_today": 0,
        "drinks_date": today,
        "food_log": [],
    }


def new_user(
    phone: str,
    jid: str,
    name: str,
    now_iso: str,
    today: str,
) -> dict[str, Any]:
    """Create a fresh user record in the ``onboarding`` state."""
    phone = normalize_phone(phone) or str(phone)
    return {
        "id": phone,
        "phone": phone,
        "jid": jid or f"{phone}@s.whatsapp.net",
        "name": (name or "").strip(),
        "created_at": now_iso,
        "updated_at": now_iso,
        "status": "onboarding",
        "onboarding_step": "goal",
        "greeted": False,
        "pending_reset": False,
        "pending_calorie_add": None,
        "notes": "",
        "profile": new_profile(),
        "plan": None,
        "last_plan_date": None,
        "plan_history": [],
        "history": [],
        "stats": new_stats(today),
        "reminders": {"daily": None, "water": None, "workout": None},
    }


def ensure_user_shape(user: dict[str, Any], today: str, now_iso: str) -> dict[str, Any]:
    """Fill in fields missing from users created by older versions."""
    base = new_user(
        str(user.get("phone") or user.get("id") or ""),
        str(user.get("jid") or ""),
        str(user.get("name") or ""),
        now_iso,
        today,
    )
    for key, value in base.items():
        if key not in user:
            user[key] = value
    if not isinstance(user.get("profile"), dict):
        user["profile"] = new_profile()
    else:
        for key, value in new_profile().items():
            user["profile"].setdefault(key, value)
    if not isinstance(user.get("stats"), dict):
        user["stats"] = new_stats(today)
    else:
        for key, value in new_stats(today).items():
            user["stats"].setdefault(key, value)
    if not isinstance(user.get("history"), list):
        user["history"] = []
    if not isinstance(user.get("plan_history"), list):
        user["plan_history"] = []
    if not isinstance(user.get("reminders"), dict):
        user["reminders"] = {"daily": None, "water": None, "workout": None}
    for key in ("daily", "water", "workout"):
        user["reminders"].setdefault(key, None)
    return user
