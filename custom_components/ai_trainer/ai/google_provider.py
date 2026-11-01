"""Google Gemini (Generative Language API) provider."""

from __future__ import annotations

import base64
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

        contents: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            if role not in {"user", "assistant"} or not message.get("content"):
                continue
            gemini_role = "model" if role == "assistant" else "user"
            text_part = str(message["content"]).strip()
            if not text_part:
                continue

            if contents and contents[-1]["role"] == gemini_role:
                contents[-1]["parts"].append({"text": text_part})
            else:
                contents.append(
                    {
                        "role": gemini_role,
                        "parts": [{"text": text_part}],
                    }
                )

        # Gemini requires that the first turn is 'user'
        while contents and contents[0]["role"] != "user":
            contents.pop(0)

        # Gemini requires that the last turn is 'user'
        while contents and contents[-1]["role"] != "user":
            contents.pop()

        if not contents:
            contents = [{"role": "user", "parts": [{"text": "שלום"}]}]

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
        return self._extract_text(data)

    async def complete_with_image(
        self,
        system: str,
        prompt: str,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        json_mode: bool = False,
    ) -> str:
        if not self.ready:
            raise AIError("ספק ה-AI לא מוגדר במלואו (חסר מפתח או מודל).")

        b64 = base64.b64encode(image_bytes).decode("ascii")
        clean_mime = (mime_type or "image/jpeg").lower()
        if clean_mime == "image/jpg":
            clean_mime = "image/jpeg"

        generation_config: dict[str, Any] = {
            "temperature": self.temperature,
            "maxOutputTokens": self.max_tokens,
        }
        if json_mode:
            generation_config["responseMimeType"] = "application/json"

        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": clean_mime,
                                "data": b64,
                            }
                        },
                        {"text": prompt},
                    ],
                }
            ],
            "generationConfig": generation_config,
        }
        data = await self._post_json(self._url(), payload, {"Content-Type": "application/json"})
        return self._extract_text(data)

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        """Extract the text from a Gemini generateContent response."""
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
