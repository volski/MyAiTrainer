"""Local Ollama provider (no API key required)."""

from __future__ import annotations

import base64
from collections.abc import Sequence
from typing import Any

from .base import AIError, AIProvider

DEFAULT_BASE = "http://homeassistant.local:11434"


class OllamaProvider(AIProvider):
    """Ollama ``/api/chat`` endpoint."""

    name = "ollama"

    def _url(self) -> str:
        base = (self.base_url or DEFAULT_BASE).rstrip("/")
        return f"{base}/api/chat"

    async def complete(
        self,
        system: str,
        messages: Sequence[dict[str, str]],
        json_mode: bool = False,
    ) -> str:
        if not self.ready:
            raise AIError("ספק ה-AI לא מוגדר במלואו (חסר מודל או כתובת).")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        if json_mode:
            payload["format"] = "json"

        data = await self._post_json(self._url(), payload, {"Content-Type": "application/json"})
        message = data.get("message") or {}
        text = str(message.get("content") or data.get("response") or "").strip()
        if not text:
            raise AIError("Ollama החזיר תשובה ריקה. ודאו שהמודל מותקן וטעון.")
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
            raise AIError("ספק ה-AI לא מוגדר במלואו (חסר מודל או כתובת).")
        b64 = base64.b64encode(image_bytes).decode("ascii")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt, "images": [b64]},
            ],
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        if json_mode:
            payload["format"] = "json"
        data = await self._post_json(self._url(), payload, {"Content-Type": "application/json"})
        message = data.get("message") or {}
        text = str(message.get("content") or data.get("response") or "").strip()
        if not text:
            raise AIError("Ollama החזיר תשובה ריקה. ודאו שהמודל מותקן וטעון.")
        return text
