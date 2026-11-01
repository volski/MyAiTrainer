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
import base64
import json
import logging
import os
import re
from collections import deque
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import aiohttp
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
    MAX_DAILY_CALORIES,
    MAX_FOOD_LOG_ITEMS,
    MAX_IMAGE_BYTES,
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
from .core.prompts import calorie_analysis_prompt, chat_messages, checkin_prompt, plan_messages
from .core.text import (
    clean_name,
    detect_command,
    format_progress_bar,
    is_affirmative,
    is_negative,
    is_water_decrease,
    normalise_hebrew,
    parse_calories_entry,
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
    "• 📸 *שלחו תמונת אוכל/שתייה* — ספירת קלוריות\n"
    "• *הוסף 400 קלוריות* — רישום קלוריות מהיר\n"
    "• *קלוריות* — סיכום הקלוריות והשתייה להיום\n"
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

MEDIA_TEXT = "כרגע אני מבין הודעות טקסט ותמונות אוכל 🙂 כתבו לי במילים או שלחו תמונה של מנה ואעריך קלוריות."

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

        media_url = ""
        for k in ("media_url", "media_path", "attachment", "url", "file", "file_path", "image", "media"):
            val = data.get(k)
            if isinstance(val, str) and val.strip():
                media_url = val.strip()
                break
        if not media_url and isinstance(raw, dict):
            for k in ("media_url", "media_path", "attachment", "url", "file", "file_path", "image", "media"):
                val = raw.get(k)
                if isinstance(val, str) and val.strip():
                    media_url = val.strip()
                    break

        media_type = ""
        for k in ("media_type", "media_mimetype", "mimetype", "mime_type"):
            val = data.get(k)
            if isinstance(val, str) and val.strip():
                media_type = val.strip().lower()
                break
        if not media_type and isinstance(raw, dict):
            for k in ("media_type", "media_mimetype", "mimetype", "mime_type"):
                val = raw.get(k)
                if isinstance(val, str) and val.strip():
                    media_type = val.strip().lower()
                    break

        if msg_type in {"image", "photo", "picture"} and not media_type:
            media_type = "image/jpeg"
        elif media_url and any(media_url.lower().endswith(ext) for ext in (".jpg", ".jpeg")):
            media_type = "image/jpeg"
        elif media_url and media_url.lower().endswith(".png"):
            media_type = "image/png"
        elif media_url and media_url.lower().endswith(".webp"):
            media_type = "image/webp"

        await self.async_handle_message(
            phone=phone,
            target=target,
            name=name,
            text=content,
            is_group=is_group,
            message_id=message_id,
            media_url=media_url,
            media_type=media_type,
            event_data=data,
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
        media_url: str = "",
        media_type: str = "",
        event_data: dict[str, Any] | None = None,
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
                    media_url=media_url,
                    media_type=media_type,
                    event_data=event_data,
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
        media_url: str = "",
        media_type: str = "",
        event_data: dict[str, Any] | None = None,
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

        # Determine whether this event carries an image.
        raw_msg = (event_data or {}).get("raw") or (event_data or {}).get("message") or {}
        has_image = bool(
            (
                media_url
                or (
                    event_data
                    and (
                        event_data.get("media_path")
                        or event_data.get("type") in {"image", "photo", "picture"}
                        or (isinstance(raw_msg, dict) and raw_msg.get("imageMessage"))
                    )
                )
            )
            and (
                (media_type or "").startswith("image")
                or any(
                    str(media_url or "").lower().endswith(ext)
                    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif")
                )
                or not media_type
            )
        )
        if not text and not has_image:
            await self.async_send(user, MEDIA_TEXT, target)
            return
        if has_image:
            await self._async_image_calorie(
                user, text, target, phone, media_url, media_type, event_data=event_data
            )
            return

        store.add_history(user, "user", text)
        store.count_message()
        stats = user.setdefault("stats", {})
        stats["messages_today"] = int(stats.get("messages_today", 0)) + 1

        # Two-step reset confirmation.
        if user.get("pending_reset"):
            if is_affirmative(text):
                await self._async_reset_user(user, target)
            else:
                user["pending_reset"] = False
                store.touch(user)
                await self.async_send(user, "בוטל — ממשיכים כרגיל 🙂", target)
            return

        # Two-step delete confirmation.
        if user.get("pending_delete"):
            if is_affirmative(text):
                await self._async_delete_user(user, target)
            else:
                user["pending_delete"] = False
                store.touch(user)
                await self.async_send(user, "בוטל — הפרופיל נשמר 🙂", target)
            return

        # Calorie confirmation: add analysed food/drink to daily count.
        pending_cal = user.get("pending_calorie_add")
        if isinstance(pending_cal, dict) and "kcal" in pending_cal:
            if is_affirmative(text) or bool(re.search(r"(עדכן|תעדכן|תוסיף|תרשום|הוסף|לעדכן|להוסיף|לרשום)", text)):
                await self._async_confirm_calories(user, pending_cal, target)
                return
            elif is_negative(text):
                user["pending_calorie_add"] = None
                store.touch(user)
                await self.async_send(user, "בוטל — המנה לא נוספה לספירה 🙂", target)
                return
            # Any other message clears the pending confirmation and continues.
            user["pending_calorie_add"] = None
            store.touch(user)

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

        # Direct text calorie entry (e.g. "הוסף 400 קלוריות", "אכלתי סלט 300 קלוריות", "+250 קלוריות")
        cal_kcal, cal_item, cal_is_drink = parse_calories_entry(text)
        if cal_kcal is not None:
            await self._async_log_manual_calories(
                user, cal_kcal, cal_item, cal_is_drink, target
            )
            return

        command = detect_command(text)
        if command == "help":
            await self.async_send(user, HELP_TEXT, target)
        elif command == "status":
            await self.async_send(user, self._status_text(user), target)
        elif command == "plan":
            await self.async_send_plan(user, target=target, force=False)
        elif command == "calories":
            await self.async_send(user, self._calories_text(user), target)
        elif command == "water":
            await self._async_water(user, text, target)
        elif command == "water_decrease":
            await self._async_water_decrease(user, text, target)
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
    # Calorie & Image Analysis
    # ------------------------------------------------------------------
    @staticmethod
    def _read_file_bytes(path: str, max_bytes: int) -> bytes:
        with open(path, "rb") as f:
            return f.read(max_bytes + 1)

    async def _async_load_image(
        self, media_url: str, event_data: dict[str, Any] | None = None
    ) -> bytes | None:
        """Download or read image bytes from a URL, local path, or WhatsApp gateway."""
        session = self.runtime._session
        raw_data = event_data or {}
        raw_msg = raw_data.get("raw") or raw_data.get("message") or {}
        if not isinstance(raw_msg, dict):
            raw_msg = {}

        # 1. Collect all potential media location strings / URLs / base64
        sources: list[str] = []
        if media_url:
            sources.append(media_url.strip())

        for k in (
            "media_url",
            "media_path",
            "attachment",
            "url",
            "file",
            "file_path",
            "image",
            "media",
            "path",
            "filename",
        ):
            for src_dict in (raw_data, raw_msg):
                val = src_dict.get(k)
                if isinstance(val, str) and val.strip() and val.strip() not in sources:
                    sources.append(val.strip())

        # 2. Check for base64 inline data
        for s in sources:
            if s.startswith("data:image/") and ";base64," in s:
                try:
                    b64_part = s.split(";base64,", 1)[1]
                    data = base64.b64decode(b64_part)
                    if 0 < len(data) <= MAX_IMAGE_BYTES:
                        _LOGGER.debug("Loaded image from data URI (%d bytes)", len(data))
                        return data
                except Exception as err:
                    _LOGGER.warning("Failed to decode base64 data URI: %s", err)

        # Also check if raw_data or raw_msg has a raw base64 string
        for k in ("base64", "image_base64", "data"):
            for src_dict in (raw_data, raw_msg):
                b64_candidate = src_dict.get(k)
                if isinstance(b64_candidate, str) and len(b64_candidate) > 200:
                    try:
                        clean_b64 = b64_candidate.split(";base64,")[-1].strip()
                        data = base64.b64decode(clean_b64)
                        if 0 < len(data) <= MAX_IMAGE_BYTES:
                            _LOGGER.debug(
                                "Loaded image from base64 field '%s' (%d bytes)",
                                k,
                                len(data),
                            )
                            return data
                    except Exception:
                        pass

        # 3. Check for absolute or relative local files on disk
        filenames: list[str] = []
        for s in sources:
            if not s.startswith(("http://", "https://", "data:")):
                base = os.path.basename(s.replace("\\", "/"))
                if base and base not in filenames:
                    filenames.append(base)
                clean_rel = s.lstrip("/\\")
                if clean_rel and clean_rel not in filenames:
                    filenames.append(clean_rel)

        file_candidates: list[str] = []
        for s in sources:
            if not s.startswith(("http://", "https://", "data:")):
                file_candidates.append(s)

        # Standard Home Assistant / Add-on paths
        config_dir = (
            self.runtime.hass.config.config_dir if self.runtime.hass else "/config"
        )
        media_dirs = [
            "/media",
            "/media/whatsapp",
            "/share",
            "/share/whatsapp",
            "/data/media",
            os.path.join(config_dir, "media"),
            os.path.join(config_dir, "media", "whatsapp"),
            os.path.join(config_dir, "www"),
            os.path.join(config_dir, "www", "whatsapp"),
        ]

        for fname in filenames:
            for mdir in media_dirs:
                file_candidates.append(os.path.join(mdir, fname))
            try:
                if self.runtime.hass:
                    file_candidates.append(
                        self.runtime.hass.config.path("media", fname)
                    )
                    file_candidates.append(
                        self.runtime.hass.config.path("www", fname)
                    )
            except Exception:
                pass

        # Check existing file candidates
        for cand in file_candidates:
            if cand and os.path.isfile(cand):
                try:
                    data = await asyncio.to_thread(
                        self._read_file_bytes, cand, MAX_IMAGE_BYTES
                    )
                    if data and 0 < len(data) <= MAX_IMAGE_BYTES:
                        _LOGGER.info(
                            "AI Trainer loaded image from local file: %s (%d bytes)",
                            cand,
                            len(data),
                        )
                        return data
                except Exception as err:
                    _LOGGER.warning("Failed to read local media file %s: %s", cand, err)

        # 4. Check HTTP / HTTPS URLs (direct and addon-hosted)
        http_urls: list[str] = []
        for s in sources:
            if s.startswith(("http://", "https://")):
                http_urls.append(s)

        # Discover WhatsApp Addon / Gateway hosts
        addon_hosts: list[str] = []
        if self.runtime.hass:
            for _, wa_entry in (
                self.runtime.hass.data.get("whatsapp") or {}
            ).items():
                if isinstance(wa_entry, dict):
                    client = wa_entry.get("client")
                    if client and getattr(client, "host", None):
                        h = str(client.host).rstrip("/")
                        if h and h not in addon_hosts:
                            addon_hosts.append(h)
            for entry in self.runtime.hass.config_entries.async_entries("whatsapp"):
                for key in ("host", "url", "addon_url"):
                    h = entry.data.get(key) or entry.options.get(key)
                    if isinstance(h, str) and h.strip():
                        h_str = h.strip().rstrip("/")
                        if h_str and h_str not in addon_hosts:
                            addon_hosts.append(h_str)

        # Default fallback hosts for ha-whatsapp addon
        for default_host in (
            "http://core-whatsapp:8000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ):
            if default_host not in addon_hosts:
                addon_hosts.append(default_host)

        # Build candidate URLs on addon hosts
        for host in addon_hosts:
            for s in sources:
                if not s.startswith(("http://", "https://", "data:")):
                    clean = s.lstrip("/\\")
                    http_urls.append(f"{host}/{clean}")
                    if not clean.startswith("media/"):
                        http_urls.append(f"{host}/media/{clean}")
            for fname in filenames:
                http_urls.append(f"{host}/media/{fname}")
                http_urls.append(f"{host}/{fname}")

        # Remove duplicates while preserving order
        seen_urls: set[str] = set()
        deduped_urls: list[str] = []
        for u in http_urls:
            if u not in seen_urls:
                seen_urls.add(u)
                deduped_urls.append(u)

        if session and not session.closed:
            for target_url in deduped_urls:
                try:
                    async with session.get(
                        target_url, timeout=aiohttp.ClientTimeout(total=15)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            if data and 0 < len(data) <= MAX_IMAGE_BYTES:
                                _LOGGER.info(
                                    "AI Trainer successfully downloaded image from %s (%d bytes)",
                                    target_url,
                                    len(data),
                                )
                                return data
                except Exception as err:
                    _LOGGER.debug("Failed candidate image URL %s: %s", target_url, err)

        _LOGGER.warning(
            "AI Trainer could not load image (tested %d file candidates, %d HTTP URLs). Sources: %s",
            len(file_candidates),
            len(deduped_urls),
            sources,
        )
        return None

    async def _async_image_calorie(
        self,
        user: dict[str, Any],
        text: str,
        target: str,
        phone: str,
        media_url: str,
        media_type: str,
        event_data: dict[str, Any] | None = None,
    ) -> None:
        """Analyze a food or drink image, estimate calories, and prompt for confirmation."""
        provider = self.runtime.provider
        if not provider or not provider.ready:
            await self.async_send(user, NO_AI_TEXT, target)
            return

        image_bytes = await self._async_load_image(media_url, event_data=event_data)
        if not image_bytes:
            await self.async_send(
                user,
                "לא הצלחתי לטעון את התמונה ששלחת 🙏 ודאו שהתמונה נשלחה כתמונה רגילה ונסו שוב.",
                target,
            )
            return

        mime = media_type or "image/jpeg"
        if not mime.startswith("image/"):
            mime = "image/jpeg"

        system, prompt = calorie_analysis_prompt(user, caption=text)
        await self._throttle_ai(user)

        try:
            raw = await provider.complete_with_image(
                system=system,
                prompt=prompt,
                image_bytes=image_bytes,
                mime_type=mime,
                json_mode=True,
            )
            parsed = parse_json_response(raw)
        except AIError as err:
            _LOGGER.warning("AI Trainer image calorie analysis failed: %s", err)
            self.runtime.logs.error("ai_error", str(err), phone)
            await self.async_send(
                user,
                "מצטער, הייתה בעיה בניתוח התמונה מול ספק ה-AI 🙏 נסו שוב בעוד רגע.",
                target,
            )
            return
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("AI Trainer unexpected image analysis failure")
            self.runtime.logs.error("ai_error", type(err).__name__, phone)
            await self.async_send(
                user, "משהו השתבש בניתוח התמונה. נסו שוב בעוד רגע 🙏", target
            )
            return

        user.setdefault("stats", {})["last_ai_at"] = dt_util.now().isoformat()

        if not isinstance(parsed, dict) or not parsed.get("item"):
            desc = str((parsed or {}).get("description") or "").strip()
            reply = (
                f"🔍 {desc}\n\nלא הצלחתי לזהות בבירור מנה או משקה בתמונה. תוכלו לכתוב לי במילים מה זה?"
                if desc
                else "🔍 לא הצלחתי לזהות אוכל או שתייה בתמונה. תוכלו לכתוב לי במילים מה אכלתם?"
            )
            await self.async_send(user, reply, target)
            return

        item = str(parsed.get("item") or "").strip()
        kcal = max(0, int(round(float(parsed.get("kcal") or 0))))
        is_drink = bool(parsed.get("is_drink"))
        description = str(parsed.get("description") or "").strip()

        user["pending_calorie_add"] = {
            "item": item,
            "kcal": kcal,
            "is_drink": is_drink,
            "description": description,
            "time": dt_util.now().isoformat(),
        }
        self.runtime.store.touch(user)

        emoji = "🥤" if is_drink else "🍽️"
        lines = [
            f"{emoji} *זיהיתי:* {item}",
            f"🔥 *הערכת קלוריות:* ~{kcal} קק\"ל",
        ]
        if description and description != item:
            lines.append(f"📝 {description}")
        lines.append("\nלהוסיף לספירה היומית שלך? כתבו *כן* או *לא*.")
        await self.async_send(user, "\n".join(lines), target)

    async def _async_confirm_calories(
        self,
        user: dict[str, Any],
        pending_cal: dict[str, Any],
        target: str,
    ) -> None:
        """Confirm adding estimated calories and food/drink to the daily count."""
        stats = user.setdefault("stats", {})
        self._reset_daily_counters(user)

        kcal = max(0, int(pending_cal.get("kcal") or 0))
        item = str(pending_cal.get("item") or "מנה").strip()
        is_drink = bool(pending_cal.get("is_drink"))

        current_cal = int(stats.get("calories_today") or 0)
        new_cal = min(current_cal + kcal, MAX_DAILY_CALORIES)
        stats["calories_today"] = new_cal
        if is_drink:
            stats["drinks_today"] = int(stats.get("drinks_today") or 0) + 1

        food_log = stats.setdefault("food_log", [])
        food_log.append(
            {
                "item": item,
                "kcal": kcal,
                "is_drink": is_drink,
                "time": dt_util.now().strftime("%H:%M"),
            }
        )
        del food_log[:-MAX_FOOD_LOG_ITEMS]

        user["pending_calorie_add"] = None
        self._touch_checkin(user)
        self.runtime.store.touch(user)

        targets = targets_for(user.get("profile") or {})
        target_cal = targets.get("calories")

        emoji = "🥤" if is_drink else "🍽️"
        lines = [
            f"✅ {emoji} נרשם: *{item}* ({kcal} קק\"ל)!",
        ]
        if target_cal:
            bar = format_progress_bar(new_cal, target_cal)
            remaining = max(0, target_cal - new_cal)
            lines.extend(
                [
                    f"📊 סה\"כ היום: *{new_cal}* מתוך *{target_cal}* קק\"ל.",
                    f"   {bar}",
                ]
            )
            if new_cal > target_cal:
                lines.append(f"⚠️ שים לב: חרגת ב-{new_cal - target_cal} קק\"ל מהיעד היומי.")
            else:
                lines.append(f"נותרו עוד כ-{remaining} קק\"ל להיום.")
        else:
            lines.append(f"📊 סה\"כ קלוריות היום: *{new_cal}* קק\"ל.")

        await self.async_send(user, "\n".join(lines), target)

    async def _async_log_manual_calories(
        self,
        user: dict[str, Any],
        kcal: int,
        item: str,
        is_drink: bool,
        target: str,
    ) -> None:
        """Directly log calories from a text command (e.g. 'הוסף 400 קלוריות')."""
        stats = user.setdefault("stats", {})
        self._reset_daily_counters(user)

        kcal = max(0, int(kcal))
        item = item.strip() or ("משקה" if is_drink else "מנה")

        current_cal = int(stats.get("calories_today") or 0)
        new_cal = min(current_cal + kcal, MAX_DAILY_CALORIES)
        stats["calories_today"] = new_cal
        if is_drink:
            stats["drinks_today"] = int(stats.get("drinks_today") or 0) + 1

        food_log = stats.setdefault("food_log", [])
        food_log.append(
            {
                "item": item,
                "kcal": kcal,
                "is_drink": is_drink,
                "time": dt_util.now().strftime("%H:%M"),
            }
        )
        del food_log[:-MAX_FOOD_LOG_ITEMS]

        self._touch_checkin(user)
        self.runtime.store.touch(user)

        targets = targets_for(user.get("profile") or {})
        target_cal = targets.get("calories")

        emoji = "🥤" if is_drink else "🍽️"
        lines = [
            f"✅ {emoji} נרשם: *{item}* ({kcal} קק\"ל)!",
        ]
        if target_cal:
            bar = format_progress_bar(new_cal, target_cal)
            remaining = max(0, target_cal - new_cal)
            lines.extend(
                [
                    f"📊 סה\"כ היום: *{new_cal}* מתוך *{target_cal}* קק\"ל.",
                    f"   {bar}",
                ]
            )
            if new_cal > target_cal:
                lines.append(f"⚠️ שים לב: חרגת ב-{new_cal - target_cal} קק\"ל מהיעד היומי.")
            else:
                lines.append(f"נותרו עוד כ-{remaining} קק\"ל להיום.")
        else:
            lines.append(f"📊 סה\"כ קלוריות היום: *{new_cal}* קק\"ל.")

        await self.async_send(user, "\n".join(lines), target)

    def _calories_text(self, user: dict[str, Any]) -> str:
        """Format the daily calorie & drinks summary."""
        self._reset_daily_counters(user)
        stats = user.get("stats") or {}
        targets = targets_for(user.get("profile") or {})
        target_cal = targets.get("calories")
        calories_today = int(stats.get("calories_today") or 0)
        drinks_today = int(stats.get("drinks_today") or 0)
        food_log = list(stats.get("food_log") or [])

        lines = ["📊 *מעקב קלוריות ושתייה יומי*"]
        if target_cal:
            bar = format_progress_bar(calories_today, target_cal)
            lines.extend(
                [
                    f"🎯 יעד יומי: {target_cal} קק\"ל",
                    f"🔥 נצרכו היום: {calories_today} קק\"ל",
                    f"   {bar}",
                ]
            )
        else:
            lines.append(f"🔥 נצרכו היום: {calories_today} קק\"ל")

        if drinks_today > 0:
            lines.append(f"🥤 משקאות שנרשמו היום: {drinks_today}")

        if food_log:
            lines.append("\n📋 *פירוט להיום:*")
            for entry in food_log:
                time_str = entry.get("time") or ""
                item_str = entry.get("item") or ""
                kcal_val = entry.get("kcal") or 0
                icon = "🥤" if entry.get("is_drink") else "🍽️"
                lines.append(f"• {icon} {item_str} — {kcal_val} קק\"ל ({time_str})")
        else:
            lines.append("\nלא נרשמו מנות היום. שלחו תמונה 📸 או כתבו למשל *הוסף 400 קלוריות*.")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    async def _async_water(
        self, user: dict[str, Any], text: str, target: str
    ) -> None:
        if is_water_decrease(text):
            await self._async_water_decrease(user, text, target)
            return

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

    async def _async_water_decrease(
        self, user: dict[str, Any], text: str, target: str
    ) -> None:
        cups = parse_water_cups(text) or 1.0
        stats = user.get("stats") or {}
        current = int(stats.get("water_ml_today") or 0)
        decrease_ml = int(round(cups * WATER_CUP_ML))
        done = max(0, current - decrease_ml)
        stats["water_ml_today"] = done
        targets = targets_for(user.get("profile") or {})
        target_ml = int(targets.get("water_ml") or 2500)
        self._touch_checkin(user)

        bar = format_progress_bar(done, target_ml)
        remaining_l = max(0.0, round((target_ml - done) / 1000.0, 1))
        lines = [
            f"💧 הורדתי {cups:g} כוסות (תיקון רישום).",
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
            lower.startswith(("אכלתי", "ארוחה", "meal", "ate", "שתיתי"))
            or any(word in lower[:30] for word in ("אכלתי", "שתיתי", "קלוריות", "ארוחת", "שווארמה", "חלבון"))
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
                "ניתן לבקש *תפריט*, לעדכן *שתייה*, לדווח *אימון* או לבקש *סטטוס*.",
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

        # Process LOG_FOOD tags from AI response
        for match_str in re.findall(r"<!--\s*LOG_FOOD:\s*(\{.*?\})\s*-->", reply, flags=re.DOTALL):
            try:
                data = json.loads(match_str)
                kcal = max(0, int(data.get("kcal") or 0))
                item = str(data.get("item") or "מנה").strip()
                is_drink = bool(data.get("is_drink"))
                if kcal > 0 or item:
                    stats = user.setdefault("stats", {})
                    self._reset_daily_counters(user)
                    current_cal = int(stats.get("calories_today") or 0)
                    stats["calories_today"] = min(current_cal + kcal, MAX_DAILY_CALORIES)
                    if is_drink:
                        stats["drinks_today"] = int(stats.get("drinks_today") or 0) + 1
                    food_log = stats.setdefault("food_log", [])
                    food_log.append(
                        {
                            "item": item,
                            "kcal": kcal,
                            "is_drink": is_drink,
                            "time": dt_util.now().strftime("%H:%M"),
                        }
                    )
                    del food_log[:-MAX_FOOD_LOG_ITEMS]
                    self._touch_checkin(user)
            except Exception as err:
                _LOGGER.warning("Failed to parse LOG_FOOD tag from AI: %s", err)

        # Process REMOVE_FOOD tags from AI response
        for match_str in re.findall(r"<!--\s*REMOVE_FOOD:\s*(\{.*?\})\s*-->", reply, flags=re.DOTALL):
            try:
                data = json.loads(match_str)
                kcal = max(0, int(data.get("kcal") or 0))
                if kcal > 0:
                    stats = user.setdefault("stats", {})
                    self._reset_daily_counters(user)
                    current_cal = int(stats.get("calories_today") or 0)
                    stats["calories_today"] = max(0, current_cal - kcal)
                    food_log = stats.setdefault("food_log", [])
                    if food_log:
                        food_log.pop()
                    self._touch_checkin(user)
            except Exception as err:
                _LOGGER.warning("Failed to parse REMOVE_FOOD tag from AI: %s", err)

        clean_reply = re.sub(
            r"<!--\s*(?:LOG_FOOD|REMOVE_FOOD):\s*\{.*?\}\s*-->\s*", "", reply, flags=re.DOTALL
        ).strip()

        user.setdefault("stats", {})["last_ai_at"] = dt_util.now().isoformat()
        if is_meal:
            self._touch_checkin(user)
        self.runtime.store.touch(user)
        await self.async_send(user, clean_reply, target)

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
        if stats.get("calories_date") != today:
            stats["calories_date"] = today
            stats["calories_today"] = 0
            stats["food_log"] = []
        if stats.get("drinks_date") != today:
            stats["drinks_date"] = today
            stats["drinks_today"] = 0

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
        cal_done = int(stats.get("calories_today") or 0)
        cal_target = targets.get("calories")
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
        if cal_target:
            lines.extend(
                [
                    f"🔥 קלוריות היום: {cal_done}/{cal_target} קק\"ל",
                    f"   {format_progress_bar(cal_done, cal_target)}",
                ]
            )
        elif cal_done:
            lines.append(f"🔥 קלוריות היום: {cal_done} קק\"ל")
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
