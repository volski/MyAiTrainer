"""Hebrew onboarding state machine.

New WhatsApp contacts are walked through three short questions: goal,
current weight and height.  Everything else has sensible defaults that can
be edited later in the panel.
"""

from __future__ import annotations

from typing import Any

from .metrics import goal_label, targets_for
from .text import clean_name, parse_goal, parse_height_cm, parse_weight_kg

NEXT_QUESTION: dict[str, str] = {
    "goal": (
        "בוא נתחיל: *מה המטרה שלך?*\n"
        "1️⃣ ירידה במשקל\n"
        "2️⃣ בניית שריר\n"
        "3️⃣ שמירה על המשקל\n"
        "4️⃣ אורח חיים בריא\n\n"
        "אפשר לענות במספר או במילים חופשיות 🙂"
    ),
    "weight": (
        "מה *המשקל הנוכחי* שלך בק\"ג?\n"
        "(למשל: 78.5)"
    ),
    "height": (
        "תודה! 📏\n"
        "ומה *הגובה* שלך בס\"מ?\n"
        "(למשל: 175)"
    ),
}

STEPS: tuple[str, ...] = ("goal", "weight", "height")


def start_onboarding(user: dict[str, Any], coach_name: str) -> str:
    """Put a user into onboarding and return the welcome message."""
    user["status"] = "onboarding"
    user["onboarding_step"] = "goal"
    user["greeted"] = True
    user["pending_reset"] = False
    name = clean_name(user.get("name"))
    coach = coach_name or "המאמן"
    return (
        f"היי {name}! 👋\n"
        f"אני *{coach}* — המאמן האישי שלך בוואטסאפ.\n"
        "אני אעזור לך עם תזונה, שתייה ואימונים, בשפה פשוטה ובעברית.\n\n"
        f"{NEXT_QUESTION['goal']}"
    )


def apply_onboarding_answer(user: dict[str, Any], text: str) -> dict[str, Any]:
    """Advance the onboarding state machine by one answer.

    Returns a dict with:
        ``reply``      message to send back (already in Hebrew)
        ``completed``  True when the profile is ready
        ``error``      True when the answer was rejected
        ``step``       the resulting onboarding step
    """
    step = str(user.get("onboarding_step") or "goal")
    profile = user.setdefault("profile", {})
    raw = str(text or "").strip()

    if step == "goal":
        goal, goal_text = parse_goal(raw)
        if goal is None:
            if len(raw) >= 2 and not raw.isdigit():
                # Free-text goal: keep it for the AI and use a safe default.
                profile["goal"] = "health"
                profile["goal_text"] = goal_text[:200]
                user["onboarding_step"] = "weight"
                return {
                    "reply": (
                        f"רשמתי: *{goal_text[:80]}* 🎯\n\n"
                        f"{NEXT_QUESTION['weight']}"
                    ),
                    "completed": False,
                    "error": False,
                    "step": "weight",
                }
            return {
                "reply": "בחרו 1–4, או כתבו את המטרה במילים (למשל: \"לרדת 5 קילו\").",
                "completed": False,
                "error": True,
                "step": step,
            }

        profile["goal"] = goal
        profile["goal_text"] = goal_text[:200]
        user["onboarding_step"] = "weight"
        return {
            "reply": f"מעולה — {goal_label(goal)} 🎯\n\n{NEXT_QUESTION['weight']}",
            "completed": False,
            "error": False,
            "step": "weight",
        }

    if step == "weight":
        weight = parse_weight_kg(raw)
        if weight is None:
            return {
                "reply": (
                    "לא הצלחתי לזהות משקל תקין 🤔\n"
                    "כתבו מספר בק\"ג, למשל: 78.5 (טווח 25–350)."
                ),
                "completed": False,
                "error": True,
                "step": step,
            }
        profile["weight_kg"] = weight
        profile["start_weight_kg"] = profile.get("start_weight_kg") or weight
        user["onboarding_step"] = "height"
        return {
            "reply": f"תודה! 📏\n\n{NEXT_QUESTION['height']}",
            "completed": False,
            "error": False,
            "step": "height",
        }

    if step == "height":
        height = parse_height_cm(raw)
        if height is None:
            return {
                "reply": (
                    "לא הצלחתי לזהות גובה תקין 🤔\n"
                    "כתבו מספר בס\"מ, למשל: 175 (טווח 100–250)."
                ),
                "completed": False,
                "error": True,
                "step": step,
            }
        profile["height_cm"] = height
        user["onboarding_step"] = "done"
        user["status"] = "active"
        return {
            "reply": onboarding_summary(user),
            "completed": True,
            "error": False,
            "step": "done",
        }

    return {
        "reply": onboarding_summary(user),
        "completed": True,
        "error": False,
        "step": "done",
    }


def onboarding_summary(user: dict[str, Any]) -> str:
    """Return the profile summary sent when onboarding completes."""
    profile = user.get("profile") or {}
    targets = targets_for(profile)
    name = clean_name(user.get("name"))
    goal = profile.get("goal_text") or goal_label(profile.get("goal"))

    lines = [
        f"מעולה {name}, יש לי את כל מה שצריך ✅",
        "",
        f"🎯 מטרה: {goal}",
        f"⚖️ משקל: {_fmt(profile.get('weight_kg'))} ק\"ג",
        f"📏 גובה: {_fmt(profile.get('height_cm'))} ס\"מ",
    ]
    if targets.get("bmi"):
        lines.append(
            f"📊 BMI: {targets['bmi']} — {targets['bmi_category']}"
        )
    if targets.get("water_l"):
        lines.append(f"💧 יעד מים: {targets['water_l']} ליטר ביום")
    if targets.get("calories"):
        lines.append(f"🔥 יעד קלורי משוער: {targets['calories']:,} קק\"ל")
    if targets.get("protein_g"):
        lines.append(f"🥩 חלבון: {targets['protein_g']} גרם")
    lines.extend(
        [
            "",
            "מעכשיו אשלח לך בכל בוקר תוכנית יומית לאוכל, שתייה ואימון.",
            "",
            "*פקודות שימושיות:*",
            "• *תפריט* — התוכנית של היום",
            "• *שתיתי 2* — תיעוד כוסות מים",
            "• *אכלתי ...* — משוב על הארוחה",
            "• *סיימתי אימון* — סימון אימון",
            "• *סטטוס* — ההתקדמות שלך",
            "• *עזרה* — כל הפקודות",
            "",
            "קדימה, מתחילים 💪",
        ]
    )
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    """Format a number without trailing ``.0``."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{number:g}"
