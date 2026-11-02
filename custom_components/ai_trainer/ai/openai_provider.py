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

    def _models_url(self) -> str:
        base = (self.base_url or DEFAULT_BASE).rstrip("/")
        if base.endswith("/chat/completions"):
            base = base.removesuffix("/chat/completions")
        parsed = urlparse(base)
        if not parsed.path or parsed.path == "/":
            base = f"{base}/v1"
        return f"{base}/models"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if "openrouter" in (self.base_url or ""):
            headers["HTTP-Referer"] = "https://github.com/volski/MyAiTrainer"
            headers["X-Title"] = "AI Personal Trainer"
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

        model = self.model
        if "deepseek" in model.lower() and "deepseek-chat" in model.lower():
            raise AIError(
                "מודל DeepSeek הנוכחי (deepseek-chat) תומך בטקסט בלבד ואינו תומך בניתוח תמונות. "
                "מומלץ לעבור ל-Google Gemini או OpenAI בהגדרות, או לכתוב לי במילים מה אכלתם."
            )
        if model == "grok-2-latest":
            model = "grok-2-vision-1212"

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
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max(1000, self.max_tokens),
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            data = await self._post_json(self._url(), payload, self._headers())
        except AIError as err:
            if json_mode and err.status in {400, 422}:
                payload.pop("response_format", None)
                data = await self._post_json(self._url(), payload, self._headers())
            else:
                raise
        return _openai_text(data)

    async def list_models(self) -> list[dict[str, str]]:
        """List models from the OpenAI / compatible endpoint."""
        url = self._models_url()
        headers = self._headers()
        try:
            import aiohttp

            async with self.session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    items = data.get("data") or data.get("models") or []
                    results = []
                    for m in items:
                        m_id = str(m.get("id") or m.get("name") or "").strip()
                        if not m_id:
                            continue
                        # Filter out audio/embedding/moderation/image-only models for OpenAI
                        if "api.openai.com" in url and any(
                            m_id.startswith(pfx)
                            for pfx in ("text-embedding", "dall-e", "whisper", "tts", "babbage", "davinci")
                        ):
                            continue
                        name = str(m.get("name") or m_id).strip()
                        results.append(
                            {"id": m_id, "name": f"{name} ({m_id})" if name != m_id else m_id}
                        )
                    if results:
                        return results
        except Exception:  # noqa: BLE001
            pass
        return self.default_models()

    def default_models(self) -> list[dict[str, str]]:
        url = (self.base_url or "").lower()
        if "openrouter" in url:
            return [
                {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet (מומלץ)"},
                {"id": "google/gemini-3.8-flash", "name": "Google Gemini 3.8 Flash"},
                {"id": "openai/gpt-4o-mini", "name": "OpenAI GPT-4o Mini"},
                {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Meta Llama 3.3 70B"},
                {"id": "deepseek/deepseek-chat", "name": "DeepSeek V3"},
            ]
        if "x.ai" in url:
            return [
                {"id": "grok-2-latest", "name": "Grok 2 Latest (מומלץ)"},
                {"id": "grok-2-vision-1212", "name": "Grok 2 Vision"},
                {"id": "grok-beta", "name": "Grok Beta"},
            ]
        if "deepseek" in url:
            return [
                {"id": "deepseek-chat", "name": "DeepSeek Chat V3 (מומלץ)"},
                {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner R1"},
            ]
        if "opencode" in url:
            return [
                {"id": "claude-3-5-sonnet", "name": "Claude 3.5 Sonnet (מומלץ)"},
                {"id": "gpt-4o", "name": "GPT-4o"},
            ]
        return [
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini (מומלץ)"},
            {"id": "gpt-4o", "name": "GPT-4o"},
            {"id": "o3-mini", "name": "o3-mini"},
        ]


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
