"""AI provider abstraction.

Providers receive a shared ``aiohttp`` session owned by the integration
runtime and return plain text.  JSON mode is a hint: callers must still
validate the output because some OpenAI-compatible servers ignore it.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any

import aiohttp


class AIError(Exception):
    """Raised when a provider cannot produce a completion."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class AIProvider:
    """Base class for chat-completion providers."""

    name = "base"

    def __init__(
        self,
        *,
        session: aiohttp.ClientSession,
        api_key: str = "",
        model: str = "",
        base_url: str = "",
        temperature: float = 0.7,
        max_tokens: int = 700,
        requires_key: bool = True,
    ) -> None:
        self.session = session
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.base_url = (base_url or "").strip()
        self.temperature = float(temperature)
        self.max_tokens = int(max_tokens)
        self.requires_key = requires_key

    @property
    def ready(self) -> bool:
        """Return True when the provider has everything it needs."""
        return bool(self.model) and (bool(self.api_key) or not self.requires_key)

    async def complete(
        self,
        system: str,
        messages: Sequence[dict[str, str]],
        json_mode: bool = False,
    ) -> str:
        """Return the assistant text for a conversation."""
        raise NotImplementedError

    async def test(self) -> str:
        """Run a very small completion to verify credentials and model."""
        return await self.complete(
            "אתה עוזר בדיקה. ענה בעברית, בקצרה.",
            [{"role": "user", "content": "ענה במילה אחת: מוכן"}],
        )

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------
    async def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        retries: int = 2,
    ) -> dict[str, Any]:
        """POST JSON with retries on transient failures.

        Error messages are sanitised: no headers, API keys or full payloads
        are ever included.
        """
        last_error: AIError | None = None
        for attempt in range(retries + 1):
            try:
                async with self.session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=90),
                ) as response:
                    body = await response.text()
                    if response.status >= 400:
                        raise AIError(
                            _extract_error(body, response.status),
                            status=response.status,
                        )
                    try:
                        data = json.loads(body)
                    except json.JSONDecodeError as err:
                        raise AIError("התקבלה תשובה לא תקינה מהספק (JSON).") from err
                    if not isinstance(data, dict):
                        raise AIError("התקבלה תשובה לא צפויה מהספק.")
                    return data
            except (TimeoutError, aiohttp.ClientError) as err:
                last_error = AIError(f"שגיאת תקשורת מול ספק ה-AI: {type(err).__name__}")
            except AIError as err:
                last_error = err
                if err.status not in {429, 500, 502, 503, 504}:
                    raise
            if attempt < retries:
                await asyncio.sleep(1.0 + attempt)

        raise last_error or AIError("שגיאה לא ידועה מול ספק ה-AI.")


def _extract_error(body: str, status: int) -> str:
    """Build a short, safe error message from a provider response."""
    detail = ""
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, dict):
                detail = str(error.get("message") or error.get("type") or "")
            elif isinstance(error, str):
                detail = error
            else:
                detail = str(data.get("message") or "")
    except (json.JSONDecodeError, TypeError):
        detail = body.strip()
    detail = " ".join(detail.split())[:280]
    if status == 401:
        return "מפתח ה-API נדחה על ידי הספק (401). בדקו את המפתח."
    if status == 429:
        return "הספק החזיר מגבלת קצב (429). נסו שוב בעוד רגע."
    prefix = f"ספק ה-AI החזיר שגיאה {status}"
    return f"{prefix}: {detail}" if detail else prefix
