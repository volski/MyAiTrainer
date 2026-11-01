"""OpenAI and OpenAI-compatible chat completions."""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlparse

from .base import AIError, AIProvider

DEFAULT_BASE = "https://api.openai.com/v1"


class OpenAIProvider(AIProvider):
    """OpenAI ``/chat/completions`` (also used for DeepSeek and compatibles)."""

    name = "openai"

    def _url(self) -> str:
        base = (self.base_url or DEFAULT_BASE).rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        parsed = urlparse(base)
        if not parsed.path or parsed.path == "/":
            base = f"{base}/v1"
        return f"{base}/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def complete(
        self,
        system: str,
        messages: Sequence[dict[str, str]],
        json_mode: bool = False,
    ) -> str:
        if not self.ready:
            raise AIError("ספק ה-AI לא מוגדר במלואו (חסר מפתח או מודל).")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            data = await self._post_json(self._url(), payload, self._headers())
        except AIError as err:
            # Some compatible servers reject response_format with a 400.
            if json_mode and err.status == 400:
                payload.pop("response_format", None)
                data = await self._post_json(self._url(), payload, self._headers())
            else:
                raise
        return _openai_text(data)

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
        data_url = f"data:{mime_type};base64,{b64}"
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            data = await self._post_json(self._url(), payload, self._headers())
        except AIError as err:
            if json_mode and err.status == 400:
                payload.pop("response_format", None)
                data = await self._post_json(self._url(), payload, self._headers())
            else:
                raise
        return _openai_text(data)


def _openai_text(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AIError("הספק לא החזיר תשובה.")
    message = (choices[0] or {}).get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        parts = [
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict)
        ]
        text = "".join(parts)
    else:
        text = str(content or "")
    text = text.strip()
    if not text:
        raise AIError("הספק החזיר תשובה ריקה.")
    return text


def parse_json_response(text: str) -> Any:
    """Parse JSON from a model response, tolerating fences and prose."""
    value = str(text or "").strip()
    if value.startswith("```"):
        value = value.strip("`")
        if value.lstrip().lower().startswith("json"):
            value = value.lstrip()[4:]
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        pass
    start = value.find("{")
    end = value.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(value[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None
