"""Local Ollama provider (no API key required)."""

from __future__ import annotations

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
