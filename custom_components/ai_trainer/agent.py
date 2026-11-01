"""The WhatsApp coach agent.

This module owns the conversation logic:

* create a user on the first inbound message
* run the Hebrew onboarding state machine
* handle commands (plan, water, workout, weight, status, pause, reset)
* answer free-text messages with the configured AI provider
* generate and deliver the daily plan
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.util import dt as dt_util

from .ai import AIError, parse_json_response
from .const import (
    CONF_ALLOW_GROUPS,
    CONF_ALLOWED_NUMBERS,
    CONF_COACH_NAME,
    CONF_ENABLE_WATER,
    CONF_MAX_USERS,
    CONF_MIN_AI_INTERVAL,
    CONF_WATER_TIMES,
    MAX_WATER_ML,
    WATER_CUP_ML,
)
from .core.metrics import targets_for
from .core.models import new_user, normalize_phone
from .core.onboarding import apply_onboarding_answer, start_onboarding
from .core.plan import (
    compose_plan_message,
    compose_water_reminder,
    fallback_plan,
    normalise_plan,
)
from .core.prompts import chat_messages, checkin_prompt, plan_messages
from .core.text import (
    clean_name,
    detect_command,
    format_progress_bar,
    normalise_hebrew,
    parse_water_cups,
    parse_weight_kg,
)

if TYPE_CHECKING:
    from .runtime import TrainerRuntime

_LOGGER = logging.getLogger(__name__)

HELP_TEXT = (
    "*הפקודות שלי* 🤖\n"
    "• *תפריט* / *תוכנית* — התוכנית של היום\n"
    "• *שתיתי 2* — תיעוד כוסות מים\n"
    "• *אכלתי ...* — משוב תזונתי\n"
    "• *סיימתי אימון* — סימון אימון\n"
    "• *שקלתי 77.5* — עדכון משקל\n"
    "• *סטטוס* — ההתקדמות שלך\n"
    "• *עצור* / *הפעל* — השהיית תזכורות\n"
    "• *איפוס* — התחלה מחדש\n"
    "• *מחק* — מחיקת הפרופיל (בלתי הפיכה)\n"
    "• *עזרה* — ההודעה הזו"
)

NO_AI_TEXT = (
    "קיבלתי 👍\n"
    "כרגע לא הוגדר ספק AI, אז אני עונה במצב בסיסי.\n\n"
    "אפשר לכתוב *תפריט* לתוכנית היומית, *שתיתי 2*, *סיימתי אימון* או *סטטוס*.\n"
    "כדי לקבל שיחה חכמה, הגדירו ספק AI בלוח הבקרה של AI Trainer."
)

MEDIA_TEXT = "כרגע אני מבין הודעות טקסט בלבד 🙂 כתבו לי במילים ואעזור."

ACCEPTED_EVENT_TYPES = {
    "chat", "text", "message", "incoming", "received", "button_reply",
    "list_reply", "poll_update", "image", "audio", "video", "document",
}


class TrainerAgent:
    """Conversation engine for one AI Trainer config entry."""

    def __init__(self, runtime: TrainerRuntime) -> None:
        self.runtime = runtime
        self._seen_ids: deque[str] = deque(maxlen=200)

    # ------------------------------------------------------------------
    # Event entry point
    # ------------------------------------------------------------------
    async def async_handle_event(self, data: dict[str, Any]) -> None:
        """Validate a WhatsApp event and dispatch it."""
        self.runtime.logs.info(
            "whatsapp_event", f"אירוע שהתקבל: {list((data or {}).keys())}"
        )
        settings = self.runtime.settings
        msg_type = str(data.get("type") or "chat").lower()
        # Be lenient: if an unknown/missing type carries a payload, treat as chat.
        if msg_type not in ACCEPTED_EVENT_TYPES:
            if msg_type and msg_type not in {"", "none", "null"}:
                # Only drop clearly non-message control events.
                if msg_type in {
                    "config_updated", "state_changed", "moderation_updated",
                    "telegram_updated", "presence", "receipt", "read",
                }:
                    return
            msg_type = "chat"

        sender = str(
            data.get("sender") or data.get("from") or data.get("chat_id") or ""
        )
        sender_number = str(
            data.get("sender_number")
            or data.get("person_number")
            or data.get("phone")
            or data.get("number")
            or ""
        )
        raw = data.get("raw") or data.get("message") or {}
        if not isinstance(raw, dict):
            raw = {}
        remote_jid = str(
            (raw.get("key") or {}).get("remoteJid")
            or data.get("remote_jid")
            or data.get("remoteJid")
            or ""
        )
        is_group = (
            "@g.us" in sender
            or "@g.us" in remote_jid
            or bool(data.get("is_group"))
        )

        if "@broadcast" in sender or "@newsletter" in sender:
            return
        if is_group and not settings.get(CONF_ALLOW_GROUPS, False):
            self.runtime.logs.info(
                "ignored", "הודעת קבוצה התעלמה (allow_groups כבוי)"
            )
            return

        phone_source = remote_jid if is_group else (sender_number or sender)
        if not phone_source and isinstance(raw, dict):
            phone_source = str((raw.get("key") or {}).get("remoteJid") or "")
        phone = normalize_phone(phone_source)
        if not phone or phone in {"me", "0"}:
            self.runtime.logs.warning(
                "ignored", f"הודעה ללא מספר שולח: {data!r}"[:300]
            )
            return

        allowed = [
            normalize_phone(number)
            for number in (settings.get(CONF_ALLOWED_NUMBERS) or [])
            if normalize_phone(number)
        ]
        if allowed and phone not in allowed:
            self.runtime.logs.info(
                "blocked", f"מספר לא מורשה ניסה לכתוב: {phone}"
            )
            return

        message_id = str(data.get("id") or (raw.get("key") or {}).get("id") or "")
        if message_id:
            if message_id in self._seen_ids:
                return
            self._seen_ids.appendleft(message_id)

        content = ""
        for key in ("content", "message", "text", "body", "conversation", "caption"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                content = value.strip()
                break
            if isinstance(value, dict):
                for sub in ("text", "body", "conversation", "caption", "content"):
                    if isinstance(value.get(sub), str) and value[sub].strip():
                        content = value[sub].strip()
                        break
            if content:
                break
        if not content:
            content = str(data.get("selected_id") or "").strip()
        if not content:
            vote = data.get("vote")
            if isinstance(vote, list):
                content = ", ".join(str(item) for item in vote)
        if not content and data.get("media_url"):
            content = ""

        target = remote_jid if is_group else (sender or f"{phone}@s.whatsapp.net")
        name = clean_name(
            data.get("sender_name") or data.get("push_name") or "",
            fallback="חבר" if not is_group else "קבוצה",
        )

        await self.async_handle_message(
            phone=phone,
            target=target,
            name=name,
            text=content,
            is_group=is_group,
            message_id=message_id,
        )

    # ------------------------------------------------------------------
    # Main message handler
    # ------------------------------------------------------------------
    async def async_handle_message(
        self,
        phone: str,
        target: str,
        name: str,
        text: str,
        is_group: bool = False,
        message_id: str = "",
    ) -> None:
        """Handle one inbound text message (already filtered)."""
        phone = normalize_phone(phone)
        if not phone:
            return
        async with self.runtime.lock_for(phone):
            try:
                await self._async_handle_locked(
                    phone=phone,
                    target=target,
                    name=name,
                    text=str(text or "").strip(),
                    is_group=is_group,
                    message_id=message_id,
                )
            except Exception as err:  # noqa: BLE001 - never kill the listener
                _LOGGER.exception("AI Trainer failed to handle message")
                self.runtime.logs.error(
                    "error", f"שגיאה בטיפול בהודעה: {type(err).__name__}", phone
                )

    async def _async_handle_locked(
        self,
        phone: str,
        target: str,
        name: str,
        text: str,
        is_group: bool,
        message_id: str,
    ) -> None:
        store = self.runtime.store
        settings = self.runtime.settings
        user = store.get_user(phone)

        if user is None:
            max_users = int(settings.get(CONF_MAX_USERS) or 25)
            if len(store.users) >= max_users:
                self.runtime.logs.warning(
                    "limit", f"נדחה משתמש חדש — הגענו למגבלת {max_users} משתמשים"
                )
                await self.runtime.bridge.async_send(
                    target,
                    "מצטער, המערכת הגיעה למספר המשתמשים המקסימלי. "
                    "פנו למנהל הבית כדי להגדיל את המגבלה.",
                )
                return
            user = store.create_user(phone, target, name if not is_group else "קבוצה")
            self.runtime.logs.info("user_created", f"נוצר משתמש חדש: {user['name'] or phone}", phone)
            store.add_history(user, "user", text or "[הודעה ללא טקסט]")
            store.count_message()
            reply = start_onboarding(user, str(settings.get(CONF_COACH_NAME) or "המאמן"))
            await self.async_send(user, reply, target)
            return

        # Keep the conversation JID and a friendly name up to date.
        if target and user.get("jid") != target:
            user["jid"] = target
        if name and not str(user.get("name") or "").strip():
            user["name"] = name
        self._reset_daily_counters(user)

        if not text:
            await self.async_send(user, MEDIA_TEXT, target)
            return

        store.add_history(user, "user", text)
        store.count_message()
        stats = user.setdefault("stats", {})
        stats["messages_today"] = int(stats.get("messages_today", 0)) + 1

        # Two-step reset confirmation.
        if user.get("pending_reset"):
            if normalise_hebrew(text) in {"כן", "מאשר", "מאשרת", "yes", "confirm", "y"}:
                await self._async_reset_user(user, target)
            else:
                user["pending_reset"] = False
                store.touch(user)
                await self.async_send(user, "בוטל — ממשיכים כרגיל 🙂", target)
            return

        # Two-step delete confirmation.
        if user.get("pending_delete"):
            if normalise_hebrew(text) in {"כן", "מאשר", "מאשרת", "yes", "confirm", "y"}:
                await self._async_delete_user(user, target)
            else:
                user["pending_delete"] = False
                store.touch(user)
                await self.async_send(user, "בוטל — הפרופיל נשמר 🙂", target)
            return

        # Allow delete/reset even during onboarding.
        command = detect_command(text)
        if command == "delete" and (
            user.get("status") == "onboarding"
            or user.get("onboarding_step") not in {None, "done"}
        ):
            user["pending_delete"] = True
            store.touch(user)
            await self.async_send(
                user,
                "⚠️ למחוק את הפרופיל (incl. כל ההיסטוריה וההתקדמות)?\n"
                "זוהי פעולה בלתי הפיכה.\n"
                "כתבו *כן* לאישור או כל דבר אחר לביטול.",
                target,
            )
            return
        if command == "reset" and (
            user.get("status") == "onboarding"
            or user.get("onboarding_step") not in {None, "done"}
        ):
            user["pending_reset"] = True
            store.touch(user)
            await self.async_send(
                user,
                "לאפס את הפרופיל וההתקדמות שלך?\n"
                "כתבו *כן* לאישור או כל דבר אחר לביטול.",
                target,
            )
            return

        if user.get("status") == "onboarding" or user.get("onboarding_step") not in {
            None,
            "done",
        }:
            result = apply_onboarding_answer(user, text)
            store.touch(user)
            await self.async_send(user, str(result["reply"]), target)
            if result["completed"]:
                await self.async_send_plan(user, target=target, force=True)
            return

        command = detect_command(text)
        if command == "help":
            await self.async_send(user, HELP_TEXT, target)
        elif command == "status":
            await self.async_send(user, self._status_text(user), target)
        elif command == "plan":
            await self.async_send_plan(user, target=target, force=False)
        elif command == "water":
            await self._async_water(user, text, target)
        elif command == "workout_done":
            await self._async_workout_done(user, target)
        elif command == "weight_update":
            await self._async_weight_update(user, text, target)
        elif command == "pause":
            user["status"] = "paused"
            store.touch(user)
            await self.async_send(
                user,
                "⏸️ תזכורות יומיות הושהו. אני עדיין כאן לכל שאלה.\n"
                "כתבו *הפעל* כדי לחזור לשגרה.",
                target,
            )
        elif command == "resume":
            user["status"] = "active"
            store.touch(user)
            await self.async_send(user, "▶️ התזכורות חזרו לפעול. קדימה! 💪", target)
        elif command == "reset":
            user["pending_reset"] = True
            store.touch(user)
            await self.async_send(
                user,
                "לאפס את הפרופיל וההתקדמות שלך?\n"
                "כתבו *כן* לאישור או כל דבר אחר לביטול.",
                target,
            )
        elif command == "delete":
            user["pending_delete"] = True
            store.touch(user)
            await self.async_send(
                user,
                "⚠️ למחוק את הפרופיל (incl. כל ההיסטוריה וההתקדמות)?\n"
                "זוהי פעולה בלתי הפיכה.\n"
                "כתבו *כן* לאישור או כל דבר אחר לביטול.",
                target,
            )
        elif command == "cancel":
            user["pending_reset"] = False
            user["pending_delete"] = False
            store.touch(user)
            await self.async_send(user, "בוטל. ממשיכים כרגיל 🙂", target)
        else:
            await self._async_general_reply(user, text, target, phone)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    async def _async_water(
        self, user: dict[str, Any], text: str, target: str
    ) -> None:
        cups = parse_water_cups(text)
        if cups is None:
            await self.async_send(
                user,
                "כמה כוסות? כתבו למשל *שתיתי 2* (כוס = 250 מ\"ל).",
                target,
            )
            return
        stats = user.get("stats") or {}
        done = int(stats.get("water_ml_today") or 0) + int(round(cups * WATER_CUP_ML))
        stats["water_ml_today"] = min(done, MAX_WATER_ML)
        targets = targets_for(user.get("profile") or {})
        target_ml = int(targets.get("water_ml") or 2500)
        done = int(stats["water_ml_today"])
        self._touch_checkin(user)

        bar = format_progress_bar(done, target_ml)
        remaining_l = max(0.0, round((target_ml - done) / 1000.0, 1))
        lines = [
            f"💧 רשמתי {cups:g} כוסות.",
            f"{bar}",
            f"היום: {round(done / 1000.0, 1)} מתוך {round(target_ml / 1000.0, 1)} ליטר.",
        ]
        if done >= target_ml:
            lines.append("הגעת ליעד המים היומי! 🎉")
        else:
            lines.append(f"נשארו {remaining_l} ליטר — בערך {int(round(remaining_l * 4))} כוסות.")
        self.runtime.store.touch(user)
        await self.async_send(user, "\n".join(lines), target)

    async def _async_workout_done(
        self, user: dict[str, Any], target: str
    ) -> None:
        today = dt_util.now().date()
        key = today.isoformat()
        stats = user.get("stats") or {}
        workouts = [str(day) for day in (stats.get("workouts") or [])]
        if key not in workouts:
            workouts.append(key)
            stats["total_workouts"] = int(stats.get("total_workouts") or 0) + 1
        stats["workouts"] = workouts[-120:]
        self._touch_checkin(user)
        self.runtime.store.touch(user)

        week_start = (today - timedelta(days=6)).isoformat()
        week_count = len([day for day in workouts if day >= week_start])
        weekly_target = targets_for(user.get("profile") or {}).get("weekly_workouts", 3)
        await self.async_send(
            user,
            (
                "✅ אימון נרשם! כל הכבוד 💪\n"
                f"השבוע: {week_count} מתוך {weekly_target} אימונים.\n"
                f"🔥 רצף: {self._streak(user)} ימים."
            ),
            target,
        )

    async def _async_weight_update(
        self, user: dict[str, Any], text: str, target: str
    ) -> None:
        weight = parse_weight_kg(text)
        if weight is None:
            await self.async_send(
                user,
                "לא זיהיתי משקל. כתבו למשל *שקלתי 77.5*.",
                target,
            )
            return
        profile = user["profile"]
        previous = profile.get("weight_kg")
        profile["weight_kg"] = weight
        if not profile.get("start_weight_kg"):
            profile["start_weight_kg"] = previous or weight
        self._touch_checkin(user)
        self.runtime.store.touch(user)
        targets = targets_for(profile)

        delta_text = ""
        if previous:
            delta = round(float(weight) - float(previous), 1)
            if delta < 0:
                delta_text = f" (ירידה של {abs(delta)} ק\"ג מהשקילה הקודמת)"
            elif delta > 0:
                delta_text = f" (עלייה של {delta} ק\"ג מהשקילה הקודמת)"
            else:
                delta_text = " (ללא שינוי)"
        lines = [
            f"⚖️ עודכן: {weight} ק\"ג{delta_text}.",
        ]
        if targets.get("bmi"):
            lines.append(f"📊 BMI: {targets['bmi']} — {targets['bmi_category']}")
        lines.append("היעדים היומיים יתעדכנו בתוכנית הבאה.")
        await self.async_send(user, "\n".join(lines), target)

    async def _async_reset_user(
        self, user: dict[str, Any], target: str, deliver: bool = True
    ) -> dict[str, Any]:
        now = dt_util.now()
        fresh = new_user(
            str(user.get("phone") or user.get("id")),
            str(user.get("jid") or target),
            str(user.get("name") or ""),
            now.isoformat(),
            now.date().isoformat(),
        )
        store = self.runtime.store
        store.users.pop(str(user.get("id") or ""), None)
        store.users[str(fresh["id"])] = fresh
        greeting = start_onboarding(
            fresh, str(self.runtime.settings.get(CONF_COACH_NAME) or "המאמן")
        )
        store.save()
        self.runtime.logs.info("reset", "המשתמש אופס", str(fresh["id"]))
        if deliver:
            await self.async_send(fresh, "🔄 איפוס הושלם.\n\n" + greeting, target)
        return fresh

    async def _async_delete_user(
        self, user: dict[str, Any], target: str, deliver: bool = True
    ) -> None:
        """Delete a user and all their data, then send a confirmation."""
        store = self.runtime.store
        phone = str(user.get("phone") or user.get("id") or "")
        name = str(user.get("name") or phone)
        store.delete_user(phone)
        store.save()
        self.runtime.logs.info("delete", f"המשתמש נמחק: {name}", phone)
        if deliver:
            await self.runtime.bridge.async_send(
                target,
                f"🗑️ הפרופיל של {name} נמחק.\n"
                "כל הנתונים וההיסטוריה נמחקו.\n"
                "אם תרצו להתחיל מחדש, просто כתבו לי 🙂",
            )

    # ------------------------------------------------------------------
    # Free text / AI
    # ------------------------------------------------------------------
    async def _async_general_reply(
        self, user: dict[str, Any], text: str, target: str, phone: str
    ) -> None:
        provider = self.runtime.provider
        if not provider or not provider.ready:
            await self.async_send(user, NO_AI_TEXT, target)
            return

        await self._throttle_ai(user)
        lower = normalise_hebrew(text)
        is_meal = bool(
            lower.startswith(("אכלתי", "ארוחה", "meal", "ate"))
            or "אכלתי" in lower[:20]
        )

        history = list(user.get("history") or [])
        if history and history[-1].get("role") == "user":
            history = history[:-1]
        system, messages = chat_messages(
            self.runtime.settings,
            user,
            user.get("plan"),
            history,
            text,
        )
        if is_meal:
            messages[-1]["content"] += "\n\n[הנחיה פנימית: " + checkin_prompt(user, text) + "]"

        try:
            reply = await provider.complete(system, messages)
        except AIError as err:
            _LOGGER.warning("AI Trainer provider error: %s", err)
            self.runtime.logs.error("ai_error", str(err), phone)
            await self.async_send(
                user,
                "מצטער, ספק ה-AI לא זמין כרגע 🙏\n"
                "אפשר לכתוב *תפריט* לתוכנית הבסיסית, *שתיתי*, *סיימתי אימון* או *סטטוס*.",
                target,
            )
            return
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("AI Trainer unexpected provider failure")
            self.runtime.logs.error("ai_error", type(err).__name__, phone)
            await self.async_send(
                user, "משהו השתבש בדרך. נסו שוב בעוד רגע 🙏", target
            )
            return

        user.setdefault("stats", {})["last_ai_at"] = dt_util.now().isoformat()
        if is_meal:
            self._touch_checkin(user)
        self.runtime.store.touch(user)
        await self.async_send(user, reply, target)

    async def _throttle_ai(self, user: dict[str, Any]) -> None:
        interval = float(self.runtime.settings.get(CONF_MIN_AI_INTERVAL) or 0)
        if interval <= 0:
            return
        last = user.get("stats", {}).get("last_ai_at")
        if not last:
            return
        try:
            previous = datetime.fromisoformat(str(last))
        except ValueError:
            return
        now = dt_util.now()
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=now.tzinfo)
        remaining = interval - (now - previous).total_seconds()
        if remaining > 0:
            await asyncio.sleep(min(remaining, interval))

    # ------------------------------------------------------------------
    # Plans
    # ------------------------------------------------------------------
    async def async_send_plan_for(
        self, phone: str, force: bool = False, deliver: bool = True
    ) -> dict[str, Any] | None:
        """Public helper used by the panel and services."""
        user = self.runtime.store.get_user(phone)
        if user is None:
            return None
        async with self.runtime.lock_for(str(user["id"])):
            return await self.async_send_plan(
                user, target=str(user.get("jid") or ""), force=force, deliver=deliver
            )

    async def async_reset_user_for(
        self, phone: str, deliver: bool = True
    ) -> dict[str, Any] | None:
        """Reset a user profile and restart onboarding."""
        user = self.runtime.store.get_user(phone)
        if user is None:
            return None
        async with self.runtime.lock_for(str(user["id"])):
            return await self._async_reset_user(
                user, str(user.get("jid") or ""), deliver=deliver
            )

    async def async_delete_user_for(
        self, phone: str, deliver: bool = True
    ) -> bool:
        """Delete a user profile and all data."""
        user = self.runtime.store.get_user(phone)
        if user is None:
            return False
        async with self.runtime.lock_for(str(user["id"])):
            await self._async_delete_user(
                user, str(user.get("jid") or ""), deliver=deliver
            )
        return True

    async def async_send_plan(
        self,
        user: dict[str, Any],
        target: str = "",
        force: bool = False,
        deliver: bool = True,
    ) -> dict[str, Any]:
        """Build (or reuse) today's plan and optionally deliver it."""
        plan = await self.async_build_plan(user, force=force)
        text = str(plan.get("text") or "")
        if deliver and text:
            await self.async_send(user, text, target or str(user.get("jid") or ""))
        return plan

    async def async_build_plan(
        self, user: dict[str, Any], force: bool = False
    ) -> dict[str, Any]:
        """Generate today's plan, using the AI provider when possible."""
        today = dt_util.now().date()
        settings = self.runtime.settings
        coach = str(settings.get(CONF_COACH_NAME) or "המאמן")
        profile = user.get("profile") or {}

        if (
            not force
            and isinstance(user.get("plan"), dict)
            and user.get("last_plan_date") == today.isoformat()
            and user["plan"].get("text")
        ):
            return user["plan"]

        plan: dict[str, Any] | None = None
        provider = self.runtime.provider
        if provider and provider.ready:
            try:
                system, messages = plan_messages(settings, user, today)
                raw = await provider.complete(system, messages, json_mode=True)
                parsed = parse_json_response(raw)
                if isinstance(parsed, dict):
                    plan = normalise_plan(parsed, profile, today, coach)
                    plan["source"] = "ai"
                else:
                    self.runtime.logs.warning(
                        "plan_fallback", "מודל ה-AI החזיר JSON לא תקין — נבנתה תוכנית בסיס"
                    )
            except AIError as err:
                _LOGGER.warning("AI Trainer plan generation failed: %s", err)
                self.runtime.logs.error("ai_error", str(err), str(user.get("id")))
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("AI Trainer plan generation crashed")
                self.runtime.logs.error("ai_error", type(err).__name__, str(user.get("id")))

        if plan is None:
            plan = fallback_plan(profile, today, coach)
            plan["source"] = "fallback"

        plan["date"] = today.isoformat()
        plan["coach_name"] = coach
        water_times = (
            list(settings.get(CONF_WATER_TIMES) or [])
            if settings.get(CONF_ENABLE_WATER)
            else []
        )
        plan["text"] = compose_plan_message(user, plan, water_times)

        self.runtime.store.remember_plan(user, plan)
        self.runtime.store.touch(user)
        self.runtime.logs.info(
            "plan",
            f"נוצרה תוכנית יומית ({'AI' if plan.get('source') == 'ai' else 'בסיס'})",
            str(user.get("id")),
        )
        return plan

    async def async_send_water_reminder(
        self, user: dict[str, Any], time_label: str = ""
    ) -> bool:
        """Send a water reminder for one user."""
        targets = targets_for(user.get("profile") or {})
        stats = user.get("stats") or {}
        done = int(stats.get("water_ml_today") or 0)
        text = compose_water_reminder(user, targets, done, time_label)
        return await self.async_send(user, text, str(user.get("jid") or ""))

    # ------------------------------------------------------------------
    # Sending and utilities
    # ------------------------------------------------------------------
    async def async_send(
        self, user: dict[str, Any], text: str, target: str = ""
    ) -> bool:
        """Send a message to the user and record it."""
        body = str(text or "").strip()
        if not body:
            return False
        recipient = target or str(user.get("jid") or "")
        if not recipient:
            recipient = f"{user.get('phone')}@s.whatsapp.net"
        ok = await self.runtime.bridge.async_send(recipient, body)
        self.runtime.store.add_history(user, "assistant", body)
        self.runtime.store.count_message()
        if ok:
            self.runtime.logs.info("sent", body.splitlines()[0][:120], str(user.get("id")))
        else:
            self.runtime.logs.warning(
                "send_failed", "ההודעה לא נשלחה (WhatsApp לא זמין?)", str(user.get("id"))
            )
        self.runtime.store.touch(user)
        return ok

    def _reset_daily_counters(self, user: dict[str, Any]) -> None:
        today = dt_util.now().date().isoformat()
        stats = user.get("stats") or {}
        if stats.get("water_date") != today:
            stats["water_date"] = today
            stats["water_ml_today"] = 0
        if stats.get("messages_date") != today:
            stats["messages_date"] = today
            stats["messages_today"] = 0

    def _touch_checkin(self, user: dict[str, Any]) -> None:
        today = dt_util.now().date()
        stats = user.get("stats") or {}
        dates = [str(day) for day in (stats.get("checkin_dates") or [])]
        if today.isoformat() not in dates:
            dates.append(today.isoformat())
        stats["checkin_dates"] = dates[-120:]
        stats["last_checkin"] = today.isoformat()

    def _streak(self, user: dict[str, Any]) -> int:
        stats = user.get("stats") or {}
        dates = {str(day) for day in (stats.get("checkin_dates") or [])}
        if not dates:
            return 0
        day = dt_util.now().date()
        if day.isoformat() not in dates:
            day -= timedelta(days=1)
        streak = 0
        while day.isoformat() in dates:
            streak += 1
            day -= timedelta(days=1)
        return streak

    def _status_text(self, user: dict[str, Any]) -> str:
        profile = user.get("profile") or {}
        stats = user.get("stats") or {}
        targets = targets_for(profile)
        self._reset_daily_counters(user)

        start = profile.get("start_weight_kg") or profile.get("weight_kg")
        current = profile.get("weight_kg")
        weight_line = "—"
        if start and current:
            delta = round(float(current) - float(start), 1)
            sign = "−" if delta < 0 else ("+" if delta > 0 else "")
            weight_line = f"{start} → {current} ק\"ג ({sign}{abs(delta)})"

        water_done = int(stats.get("water_ml_today") or 0)
        water_target = int(targets.get("water_ml") or 2500)
        today = dt_util.now().date()
        week_start = (today - timedelta(days=6)).isoformat()
        week_workouts = len(
            [day for day in (stats.get("workouts") or []) if str(day) >= week_start]
        )

        lines = [
            "📊 *ההתקדמות שלך*",
            f"🎯 מטרה: {profile.get('goal_text') or targets.get('goal_label')}",
            f"⚖️ משקל: {weight_line}",
        ]
        if targets.get("bmi"):
            lines.append(f"📊 BMI: {targets['bmi']} — {targets['bmi_category']}")
        lines.extend(
            [
                f"💧 מים היום: {round(water_done / 1000.0, 1)}/{round(water_target / 1000.0, 1)} ליטר",
                f"   {format_progress_bar(water_done, water_target)}",
                f"🏋️ אימונים השבוע: {week_workouts}/{targets.get('weekly_workouts', 3)}",
                f"🔥 רצף: {self._streak(user)} ימים",
            ]
        )
        if user.get("last_plan_date"):
            lines.append(f"🗓️ תוכנית אחרונה: {user['last_plan_date']}")
        if user.get("status") == "paused":
            lines.append("⏸️ התזכורות מושהות — כתבו *הפעל* לחזרה.")
        return "\n".join(lines)
