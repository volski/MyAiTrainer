"""Google Gemini (Generative Language API) provider."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from urllib.parse import quote

from .base import AIError, AIProvider

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"


class GoogleProvider(AIProvider):
    """Gemini models via ``generateContent``."""

    name = "google"

    def _url(self) -> str:
        model = self.model.removeprefix("models/")
        return f"{API_ROOT}/{quote(model, safe='')}:generateContent?key={self.api_key}"

    async def complete(
        self,
        system: str,
        messages: Sequence[dict[str, str]],
        json_mode: bool = False,
    ) -> str:
        if not self.ready:
            raise AIError("ספק ה-AI לא מוגדר במלואו (חסר מפתח או מודל).")

        contents = []
        for message in messages:
            role = message.get("role")
            if role not in {"user", "assistant"} or not message.get("content"):
                continue
            contents.append(
                {
                    "role": "model" if role == "assistant" else "user",
                    "parts": [{"text": str(message["content"])}],
                }
            )

        generation_config: dict[str, Any] = {
            "temperature": self.temperature,
            "maxOutputTokens": self.max_tokens,
        }
        if json_mode:
            generation_config["responseMimeType"] = "application/json"

        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": generation_config,
        }
        data = await self._post_json(self._url(), payload, {"Content-Type": "application/json"})

        feedback = data.get("promptFeedback") or {}
        if feedback.get("blockReason"):
            raise AIError("הבקשה נחסמה על ידי ספק ה-AI.")

        candidates = data.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise AIError("הספק לא החזיר תשובה.")
        candidate = candidates[0] or {}
        content = candidate.get("content") or {}
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            raise AIError("הספק החזיר תשובה ריקה.")
        text = "".join(
            str(part.get("text") or "") for part in parts if isinstance(part, dict)
        ).strip()
        if not text:
            raise AIError("הספק החזיר תשובה ריקה.")
        return text
