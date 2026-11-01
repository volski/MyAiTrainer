"""Anthropic Messages API provider."""

from __future__ import annotations

import base64
from collections.abc import Sequence
from typing import Any

from .base import AIError, AIProvider

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicProvider(AIProvider):
    """Claude models through the Messages API."""

    name = "anthropic"

    async def complete(
        self,
        system: str,
        messages: Sequence[dict[str, str]],
        json_mode: bool = False,
    ) -> str:
        if not self.ready:
            raise AIError("ספק ה-AI לא מוגדר במלואו (חסר מפתח או מודל).")

        clean_messages = [
            {"role": message["role"], "content": str(message["content"])}
            for message in messages
            if message.get("role") in {"user", "assistant"} and message.get("content")
        ]
        system_prompt = system
        if json_mode:
            system_prompt += (
                "\n\nהחזר JSON תקין בלבד, בלי טקסט נוסף ובלי גדרות קוד."
            )

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": system_prompt,
            "messages": clean_messages,
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }
        data = await self._post_json(API_URL, payload, headers)
        content = data.get("content")
        if not isinstance(content, list):
            raise AIError("הספק לא החזיר תשובה.")
        parts = [
            str(block.get("text") or "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = "".join(parts).strip()
        if not text:
            raise AIError("הספק החזיר תשובה ריקה.")
        return text

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
        media_type = mime_type or "image/jpeg"
        system_prompt = system
        if json_mode:
            system_prompt += (
                "\n\nהחזר JSON תקין בלבד, בלי טקסט נוסף ובלי גדרות קוד."
            )
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }
        data = await self._post_json(API_URL, payload, headers)
        content = data.get("content")
        if not isinstance(content, list):
            raise AIError("הספק לא החזיר תשובה.")
        parts = [
            str(block.get("text") or "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = "".join(parts).strip()
        if not text:
            raise AIError("הספק החזיר תשובה ריקה.")
        return text
