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
    value = re.sub(r"\bשתתי\b", "שתיתי", value)
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
    elif re.search(r"\b(כוס|כוסית|כוסות|cup|cups|glass)\b", value):
        cups = 1.0
    elif re.search(r"\b(בקבוק|בקבוקים|bottle|bottles)\b", value):
        cups = 2.0
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


def is_affirmative(text: Any) -> bool:
    """Return True if text expresses confirmation (Hebrew or English)."""
    raw = str(text or "").strip()
    if any(emoji in raw for emoji in ("👍", "👌", "✔️", "✅")):
        return True
    val = normalise_hebrew(raw)
    val = re.sub(r"[^\w\s]", "", val).strip()
    if not val:
        return False
    affirmative_words = {
        "כן", "מאשר", "מאשרת", "אישור", "תוסיף", "הוסף", "תוסיפי",
        "תרשום", "רשום", "תרשמי", "עדכן", "תעדכן", "עדכני", "תעדכני",
        "ספור", "תספור", "תספרי", "סבבה", "בטח", "אחלה", "מעולה",
        "טוב", "אוקי", "יאללה", "קדימה", "yes", "y", "ok", "okay",
        "sure", "yep", "yeah", "1", "נכון", "בכיף",
    }
    if val in affirmative_words:
        return True
    first_word = val.split()[0]
    return first_word in affirmative_words


def is_negative(text: Any) -> bool:
    """Return True if text expresses refusal or cancellation."""
    raw = str(text or "").strip()
    if any(emoji in raw for emoji in ("👎", "❌", "✖️")):
        return True
    val = normalise_hebrew(raw)
    val = re.sub(r"[^\w\s]", "", val).strip()
    if not val:
        return False
    negative_words = {
        "לא", "בטל", "ביטול", "אל", "ותר", "וותר",
        "no", "n", "cancel", "stop", "nope", "0", "עזוב", "עזבי",
    }
    if val in negative_words:
        return True
    first_word = val.split()[0]
    return first_word in negative_words


NON_WATER_DRINKS: tuple[str, ...] = (
    "קפה",
    "אספרסו",
    "נס קפה",
    "קפוצינו",
    "קפוצ'ינו",
    "אמריקנו",
    "מקיאטו",
    "הפוך",
    "שחור",
    "תה",
    "שוקו",
    "מיץ",
    "שייק",
    "סמוטי",
    "סמודי",
    "פרו",
    "חלבון",
    "משקה חלבון",
    "אבקת חלבון",
    "בירה",
    "יין",
    "אלכוהול",
    "וודקה",
    "וויסקי",
    "ערק",
    "קוקטייל",
    "קולה",
    "זירו",
    "פאנטה",
    "ספרייט",
    "חלב",
    "סויה",
    "שיבולת שועל",
    "שקדים",
    "coffee",
    "espresso",
    "tea",
    "juice",
    "shake",
    "smoothie",
    "protein",
    "beer",
    "wine",
    "alcohol",
    "milk",
    "coke",
)


def is_question(text: Any) -> bool:
    """Return True if the text is asking a question."""
    raw = str(text or "").strip()
    if not raw:
        return False
    if "?" in raw or "？" in raw:
        return True
    val = normalise_hebrew(raw)
    question_starters = (
        "האם",
        "למה",
        "מדוע",
        "איך",
        "כיצד",
        "מתי",
        "איפה",
        "אן",
        "אנה",
        "נחשב",
        "נחשבת",
        "נחשבים",
        "נכנס תחת",
        "נכנסת תחת",
        "נכנסים תחת",
        "מה זה",
        "מהו",
        "מהי",
        "מהם",
        "האם מותר",
        "מותר ל",
        "אפשר ל",
        "אפשר לקבל",
        "why",
        "how",
        "what",
        "when",
        "where",
        "is it",
        "can i",
        "does",
    )
    for starter in question_starters:
        if val == starter or val.startswith(starter + " ") or val.startswith(starter + ":"):
            return True
    if re.search(r"\b(נחשב ל|נחשב כמו|נכנס תחת)\b", val):
        return True
    return False


def is_water_decrease(text: Any) -> bool:
    """Return True if text asks to reduce, subtract or remove water."""
    val = normalise_hebrew(text)
    decrease_words = (
        "תוריד",
        "הורד",
        "להוריד",
        "מחק",
        "למחוק",
        "בטעות",
        "טעות",
        "פחות",
        "מינוס",
        "-",
        "הפחת",
        "להפחית",
        "הסר",
        "להסיר",
        "reduce",
        "decrease",
        "remove",
        "minus",
        "subtract",
    )
    return any(w in val for w in decrease_words)


def parse_calories_entry(text: Any) -> tuple[int | None, str, bool]:
    """Parse calories, item description, and is_drink flag from text.

    Returns (kcal, item, is_drink) or (None, "", False) if not matched.
    """
    raw = str(text or "").strip()
    norm = normalise_hebrew(raw)
    if not norm:
        return None, "", False

    # Check for drink indicators
    is_drink = bool(re.search(r"(שתיתי|שתיה|שתייה|משקה|מיץ|קפה|שייק|תה|קולה|סודה|drink|drank)", norm))

    # Pattern 1: אכלתי/שתיתי [item] [number] קלוריות / קק"ל
    m = re.search(r"(?:אכלתי|שתיתי|ארוחה|מנה)\s+(.+?)\s+(\d{1,4})\s*(?:קלוריות|קקל|קק\"ל|קק״ל|kcal)", norm)
    if m:
        kcal = int(m.group(2))
        item = m.group(1).strip()
        if 1 <= kcal <= 10000 and item:
            return kcal, item, is_drink

    # Pattern 2: הוסף/רשום/ספור [number] קלוריות [item optional]
    m = re.search(r"(?:הוסף|הוספתי|תרשום|רשום|ספור|ספר|\+)\s*(\d{1,4})\s*(?:קלוריות|קקל|קק\"ל|קק״ל|kcal)(?:\s+(?:על|עבור|של)?\s*(.+))?", norm)
    if m:
        kcal = int(m.group(1))
        item = (m.group(2) or "").strip() or ("משקה" if is_drink else "מנה")
        if 1 <= kcal <= 10000:
            return kcal, item, is_drink

    # Pattern 3: [number] קלוריות [item optional]
    m = re.search(r"^(\d{1,4})\s*(?:קלוריות|קקל|קק\"ל|קק״ל|kcal)(?:\s+(?:על|עבור|של)?\s*(.+))?$", norm)
    if m:
        kcal = int(m.group(1))
        item = (m.group(2) or "").strip() or ("משקה" if is_drink else "מנה")
        if 1 <= kcal <= 10000:
            return kcal, item, is_drink

    # Pattern 4: אכלתי/שתיתי [item] [number] (e.g. "אכלתי טוסט 300")
    m = re.search(r"(?:אכלתי|שתיתי)\s+(.+?)\s+(\d{2,4})$", norm)
    if m:
        kcal = int(m.group(2))
        item = m.group(1).strip()
        if 20 <= kcal <= 5000 and item:
            return kcal, item, is_drink

    return None, "", False


def detect_command(text: Any) -> str | None:
    """Return a command key for a message, or ``None`` for normal chat."""
    value = normalise_hebrew(text)
    if not value:
        return None

    # Error message quotes or forwarded system notices should never trigger commands
    if value.startswith(("מצטער", "ספק ה-ai", "הספק לא", "שגיאה", "error")):
        return None

    # Exact single punctuation / help
    if re.search(r"^(עזרה|help|פקודות|\?)$", value):
        return "help"

    # A question should be answered conversationally by the AI, never misclassified as a command
    if is_question(text):
        return None

    # A meal log is conversational: let the AI answer it, even if the text
    # also mentions water.
    if re.match(r"^(אכלתי|כלתי|ארוחה|meal|ate)\b", value):
        return None

    # Water decrease/removal
    if is_water_decrease(value) and re.search(r"(כוס|כוסות|מים|water|ליטר|מ\"ל|מ״ל|cup|cups)", value):
        return "water_decrease"

    # Non-water drinks (coffee, espresso, tea, protein shake, etc.) are conversational / food log, NOT pure water
    if any(drink in value for drink in NON_WATER_DRINKS):
        return None

    if re.search(r"^(סטטוס|מצב|התקדמות|status)\b", value):
        return "status"

    # Workout completed: match explicit workout declarations, not random sentences containing words
    if re.match(
        r"^(?:כן,?\s*)?(?:סיימתי אימון|אימון בוצע|עשיתי אימון|התאמנתי|סיימתי את האימון|done workout|workout done)(?:\s*(?:היום|עכשיו|💪|!|\.))*$",
        value,
    ):
        return "workout_done"

    # Water logging: match explicit drinking statements or cup quantities, not random sentences
    if re.match(r"^(?:שתיתי|שתתי|שתיה|שתייה|מים|כוס|water|drank)\b", value) or (
        parse_water_cups(value) is not None
        and re.search(r"\b(שתיתי|שתתי|מים|כוס|כוסות|ליטר|מ\"ל|מ״ל|water|drank)\b", value)
    ):
        return "water"

    # Weight update
    if re.match(r"^(?:שקלתי|עדכן משקל|משקל חדש|update weight|weighed)\b", value) or (
        re.search(r"\b(שקלתי|עדכן משקל|משקל חדש)\b", value) and parse_weight_kg(value) is not None
    ):
        return "weight_update"

    # Plan
    if re.match(r"^(?:תפריט|תוכנית|תכנית|מה לאכול|daily plan|menu)(\b|$)", value):
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
