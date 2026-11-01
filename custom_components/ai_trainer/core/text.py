"""Hebrew text normalisation and intent parsing.

WhatsApp users type freely: niqqud, emoji, English words, commas as decimal
separators, "1.5 ליטר", "78 קילו" and so on.  These helpers turn that into
strict values while keeping the parsing deterministic and testable.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

_NIQQUD = re.compile(r"[\u0591-\u05BD\u05BF\u05C1\u05C2\u05C4\u05C5\u05C7]")
_WHITESPACE = re.compile(r"\s+")
_NUMBER = re.compile(r"(\d{1,4}(?:[.,]\d{1,2})?)")
_LITRES = re.compile(r"ליטר|liter|litre")
_MILLILITRES = re.compile(r"מיליליטר|מ״ל|מ\"ל|\bml\b")
_POUNDS = re.compile(r"פאונד|pound|\blbs?\b")

GOAL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "build_muscle": (
        "שריר",
        "מסה",
        "להתחזק",
        "לעלות",
        "להעלות",
        "bulk",
        "muscle",
        "gain",
    ),
    "lose_weight": (
        "לרדת",
        "ירידה",
        "להרזות",
        "הרזיה",
        "לרזות",
        "לחטב",
        "חיטוב",
        "lose",
        "cut",
        "slim",
    ),
    "maintain": (
        "לשמור",
        "שמירה",
        "יציב",
        "תחזוקה",
        "maintain",
        "keep",
    ),
    "health": (
        "בריא",
        "בריאות",
        "כושר",
        "אנרגיה",
        "הרגלים",
        "health",
        "healthy",
        "fitness",
    ),
}

WEEKDAYS_HE: tuple[str, ...] = (
    "שני",
    "שלישי",
    "רביעי",
    "חמישי",
    "שישי",
    "שבת",
    "ראשון",
)


def normalise_hebrew(text: Any) -> str:
    """Lowercase, strip niqqud/emoji digits and collapse whitespace."""
    value = str(text or "")
    value = value.replace("\ufe0f", "").replace("\u20e3", "")
    value = _NIQQUD.sub("", value)
    value = value.replace("\u05f3", "'").replace("\u05f4", '"')
    value = value.replace("־", "-").replace("–", "-").replace("—", "-")
    value = value.lower()
    return _WHITESPACE.sub(" ", value).strip()


def _number_in(text: str) -> float | None:
    match = _NUMBER.search(text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def parse_weight_kg(text: Any) -> float | None:
    """Parse a body weight in kilograms (pounds are converted)."""
    value = normalise_hebrew(text)
    number = _number_in(value)
    if number is None:
        return None
    if _POUNDS.search(value):
        number = number / 2.20462
    if number < 25 or number > 350:
        return None
    return round(number, 1)


def parse_height_cm(text: Any) -> int | None:
    """Parse a height in centimetres.

    Accepts ``175``, ``1.75``, ``1,75 מטר`` and feet/inches such as ``5'9"``.
    """
    value = normalise_hebrew(text)

    feet = re.search(r"(\d)\s*'\s*(\d{1,2})\s*\"?", value)
    if feet:
        total_cm = (int(feet.group(1)) * 12 + int(feet.group(2))) * 2.54
        return int(round(total_cm)) if 100 <= total_cm <= 250 else None

    number = _number_in(value)
    if number is None:
        return None
    if 0.9 <= number <= 2.5:
        number *= 100
    if number < 100 or number > 250:
        return None
    return int(round(number))


def parse_water_cups(text: Any) -> float | None:
    """Parse a water amount and return it in 250 ml cups."""
    value = normalise_hebrew(text)
    number = _number_in(value)

    if _MILLILITRES.search(value) and number is not None:
        cups = number / 250.0
    elif _LITRES.search(value) and number is not None:
        cups = number * 4.0
    elif number is not None:
        cups = number
    elif "חצי" in value or "half" in value:
        cups = 0.5
    elif value:
        cups = 1.0
    else:
        return None

    if cups <= 0 or cups > 12:
        return None
    return round(cups * 2) / 2


def parse_goal(text: Any) -> tuple[str | None, str]:
    """Classify a free-text goal.

    Returns ``(goal_key, original_text)``.  ``goal_key`` is ``None`` when the
    text is usable as a custom goal but does not match a known category.
    """
    value = normalise_hebrew(text)
    if not value:
        return None, ""
    compact = re.sub(r"[^\w\d]", "", value)
    if compact in {"1", "2", "3", "4"}:
        return {
            "1": "lose_weight",
            "2": "build_muscle",
            "3": "maintain",
            "4": "health",
        }[compact], str(text).strip()

    for goal, keywords in GOAL_KEYWORDS.items():
        if any(keyword in value for keyword in keywords):
            return goal, str(text).strip()
    return None, str(text).strip()


def detect_command(text: Any) -> str | None:
    """Return a command key for a message, or ``None`` for normal chat."""
    value = normalise_hebrew(text)
    if not value:
        return None

    # A meal log is conversational: let the AI answer it, even if the text
    # also mentions water.
    if re.match(r"^(אכלתי|ארוחה|meal|ate)\b", value):
        return None

    if re.search(r"^(עזרה|help|פקודות|\?)$", value):
        return "help"
    if re.search(r"^(סטטוס|מצב|התקדמות|status)\b", value):
        return "status"
    if re.search(r"(סיימתי אימון|אימון בוצע|עשיתי אימון|התאמנתי|done workout|workout done)", value):
        return "workout_done"
    if re.search(r"(שתיתי|שתיה|שתייה|מים|כוס|water|drank)", value):
        return "water"
    if re.search(r"(שקלתי|עדכן משקל|משקל חדש|update weight|weighed)", value):
        return "weight_update"
    if re.search(r"(תפריט|תוכנית|תכנית|מה לאכול|daily plan|menu)", value):
        return "plan"
    if re.search(r"^(קלוריות|סיכום אכילה|כמה אכלתי|calories|calorie)(\b|$)", value):
        return "calories"
    if re.search(r"^(עצור|הפסק|תשתוק|stop|pause)\b", value):
        return "pause"
    if re.search(r"^(הפעל|תחזור|resume|start)\b", value):
        return "resume"
    if re.search(r"^(איפוס|אפס|reset|התחל מחדש)\b", value):
        return "reset"
    if re.search(r"^(מחק|מחיקה|delete|remove|הסר|הסרה)\b", value):
        return "delete"
    if re.search(r"^(ביטול|cancel)\b", value):
        return "cancel"
    return None


def format_progress_bar(done: float, total: float, width: int = 10) -> str:
    """Return a text progress bar such as ``▰▰▰▱▱▱▱▱▱▱ 30%``."""
    if total <= 0:
        return ""
    ratio = max(0.0, min(1.0, float(done) / float(total)))
    filled = int(round(ratio * width))
    return "▰" * filled + "▱" * (width - filled) + f" {int(round(ratio * 100))}%"


def weekday_he(day: date) -> str:
    """Return the Hebrew weekday name for a date."""
    return WEEKDAYS_HE[day.weekday()]


def clean_name(value: Any, fallback: str = "חבר") -> str:
    """Return a safe display name for greetings."""
    name = _WHITESPACE.sub(" ", str(value or "")).strip()
    if not name or name.lower() in {"me", "you", "whatsapp"}:
        return fallback
    return name[:40]


def trim_message(text: str, limit: int = 3600) -> str:
    """Trim a message to a WhatsApp-friendly length."""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def split_message(text: str, limit: int = 3500) -> list[str]:
    """Split a long message on line boundaries without breaking words."""
    value = str(text or "").strip()
    if len(value) <= limit:
        return [value] if value else []
    chunks: list[str] = []
    current = ""
    for line in value.splitlines(keepends=True):
        if len(current) + len(line) <= limit:
            current += line
            continue
        if current:
            chunks.append(current.rstrip())
            current = ""
        if len(line) <= limit:
            current = line
            continue
        # A single very long line: hard-split it.
        for start in range(0, len(line), limit):
            piece = line[start : start + limit]
            if len(current) + len(piece) <= limit:
                current += piece
            else:
                if current:
                    chunks.append(current.rstrip())
                current = piece
    if current.strip():
        chunks.append(current.rstrip())
    return chunks
