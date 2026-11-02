"""Hebrew onboarding state machine.

New WhatsApp contacts are walked through six short questions:
1. Goal (ירידה במשקל / בניית שריר / שמירה / אורח חיים בריא)
2. Sex / Gender (גבר / אישה — משפיע ישירות על חישוב ה-BMI, הרכב הגוף וקצב חילוף החומרים)
3. Age / Date of birth (גיל או שנת לידה)
4. Current weight (משקל נוכחי בק"ג)
5. Height (גובה בס"מ)
6. Target weight (משקל יעד בק"ג)

After collecting these, the bot computes BMI and metabolic baselines, builds a
personalized roadmap to arrive at the target weight, and splits it into realistic
progressive milestones.
"""

from __future__ import annotations

import re
from typing import Any

from .metrics import build_weight_plan, goal_label, targets_for
from .text import (
    clean_name,
    parse_age_or_dob,
    parse_goal,
    parse_height_cm,
    parse_sex,
    parse_weight_kg,
)

NEXT_QUESTION: dict[str, str] = {
    "goal": (
        "בוא נתחיל: *מה המטרה העיקרית שלך?* 🎯\n"
        "1️⃣ ירידה במשקל\n"
        "2️⃣ בניית שריר וחיטוב\n"
        "3️⃣ שמירה על המשקל\n"
        "4️⃣ אורח חיים בריא וכושר\n\n"
        "אפשר לענות במספר (1–4) או במילים חופשיות 🙂"
    ),
    "sex": (
        "כדי להתאים במדויק את מדדי ה-BMI, הרכב הגוף, שריפת הקלוריות והיעדים:\n"
        "*מה המין שלך?* 👤\n"
        "1️⃣ גבר\n"
        "2️⃣ אישה\n\n"
        "(מדדי BMI וחילוף חומרים נבדלים פיזיולוגית בין גברים לנשים)"
    ),
    "age": (
        "מעולה! ומה *הגיל* שלך? 🎂\n"
        "(אפשר לכתוב גיל, למשל: *28*, או שנת לידה, למשל: *1996*)"
    ),
    "weight": (
        "מה *המשקל הנוכחי* שלך בק\"ג? ⚖️\n"
        "(למשל: *78.5*)"
    ),
    "height": (
        "תודה! 📏\n"
        "ומה *הגובה* שלך בס\"מ?\n"
        "(למשל: *175*)"
    ),
    "target_weight": (
        "מעולה! ומה *משקל היעד* שתרצה/י להגיע אליו בק\"ג? 🎯\n"
        "(למשל: *72* — אם המטרה היא שמירה, אפשר לכתוב את המשקל הנוכחי או 'שמירה')"
    ),
}

STEPS: tuple[str, ...] = (
    "goal",
    "sex",
    "age",
    "weight",
    "height",
    "target_weight",
)


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
                user["onboarding_step"] = "sex"
                return {
                    "reply": (
                        f"רשמתי: *{goal_text[:80]}* 🎯\n\n"
                        f"{NEXT_QUESTION['sex']}"
                    ),
                    "completed": False,
                    "error": False,
                    "step": "sex",
                }
            return {
                "reply": "בחרו 1–4, או כתבו את המטרה במילים (למשל: \"לרדת 5 קילו\").",
                "completed": False,
                "error": True,
                "step": step,
            }

        profile["goal"] = goal
        profile["goal_text"] = goal_text[:200]
        user["onboarding_step"] = "sex"
        return {
            "reply": f"מעולה — {goal_label(goal)} 🎯\n\n{NEXT_QUESTION['sex']}",
            "completed": False,
            "error": False,
            "step": "sex",
        }

    if step == "sex":
        sex = parse_sex(raw)
        if sex is None:
            return {
                "reply": (
                    "לא הצלחתי לזהות 🤔\n"
                    "כתבו *1* לגבר או *2* לאישה (או במילים: גבר / אישה).\n"
                    "מדדי ה-BMI, הרכב הגוף וקצב חילוף החומרים מחושבים בהתאם 👤"
                ),
                "completed": False,
                "error": True,
                "step": step,
            }
        profile["sex"] = sex
        user["onboarding_step"] = "age"
        sex_str = "גבר" if sex == "male" else "אישה"
        return {
            "reply": f"רשמתי, {sex_str} 👍\n\n{NEXT_QUESTION['age']}",
            "completed": False,
            "error": False,
            "step": "age",
        }

    if step == "age":
        age = parse_age_or_dob(raw)
        if age is None:
            return {
                "reply": (
                    "לא הצלחתי לזהות גיל תקין 🤔\n"
                    "כתבו מספר גיל (בין 12 ל-100), או שנת לידה (למשל: 1994)."
                ),
                "completed": False,
                "error": True,
                "step": step,
            }
        profile["age"] = age
        user["onboarding_step"] = "weight"
        return {
            "reply": f"מעולה, גיל {age} 🎯\n\n{NEXT_QUESTION['weight']}",
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
        user["onboarding_step"] = "target_weight"
        return {
            "reply": f"רשמתי {height} ס\"מ! 📏\n\n{NEXT_QUESTION['target_weight']}",
            "completed": False,
            "error": False,
            "step": "target_weight",
        }

    if step == "target_weight":
        if re.search(
            r"\b(שמירה|אותו דבר|נוכחי|כמו עכשיו|הנוכחי|שמור|לשמור|same|current|maintain)\b",
            raw.lower(),
        ):
            target_weight = profile.get("weight_kg")
        else:
            target_weight = parse_weight_kg(raw)

        if target_weight is None:
            return {
                "reply": (
                    "לא הצלחתי לזהות משקל יעד 🤔\n"
                    "כתבו מספר בק\"ג (למשל: 72), או \"שמירה\" כדי להישאר במשקל הנוכחי."
                ),
                "completed": False,
                "error": True,
                "step": step,
            }

        profile["target_weight_kg"] = target_weight
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
    """Return the profile summary and roadmap plan sent when onboarding completes."""
    profile = user.get("profile") or {}
    targets = targets_for(profile)
    name = clean_name(user.get("name"))
    goal = profile.get("goal_text") or goal_label(profile.get("goal"))
    sex = str(profile.get("sex") or "unspecified")
    age = int(profile.get("age") or 30)
    weight = profile.get("weight_kg")
    height = profile.get("height_cm")
    target_weight = profile.get("target_weight_kg") or weight

    sex_str = "גבר" if sex == "male" else ("אישה" if sex == "female" else "")
    sex_age_part = f"{sex_str}, גיל {age}" if sex_str else f"גיל {age}"

    plan_data = build_weight_plan(
        current_weight=weight,
        target_weight=target_weight,
        height_cm=height,
        sex=sex,
        age=age,
        goal=str(profile.get("goal") or "lose_weight"),
    )
    if plan_data.get("milestones"):
        profile["milestones"] = plan_data["milestones"]

    lines = [
        f"מעולה {name}! יש לי את כל המידע ובניתי לך תוכנית אישית 🎯",
        "",
        f"👤 *פרופיל אישי:* {sex_age_part}",
        f"🎯 *מטרה:* {goal}",
        f"⚖️ *משקל נוכחי:* {_fmt(weight)} ק\"ג | 📏 *גובה:* {_fmt(height)} ס\"מ",
    ]

    if target_weight:
        lines.append(f"🏁 *משקל יעד:* {_fmt(target_weight)} ק\"ג")

    if targets.get("bmi"):
        bmi_line = f"📊 *BMI נוכחי:* {targets['bmi']} — {targets['bmi_category']}"
        if plan_data.get("target_bmi"):
            bmi_line += f" ⬅️ יעד: {plan_data['target_bmi']}"
        lines.append(bmi_line)

    h_min = plan_data.get("healthy_weight_min")
    h_max = plan_data.get("healthy_weight_max")
    if h_min and h_max:
        lines.append(f"💡 טווח משקל מומלץ לגובה שלך: {h_min}–{h_max} ק\"ג")

    milestones = plan_data.get("milestones") or []
    delta = plan_data.get("delta_kg", 0.0)
    weeks = plan_data.get("estimated_weeks", 0)

    if milestones:
        lines.append("")
        if delta < -0.5:
            lines.append(f"🗺️ *מפת הדרך ליעד שלך (ירידה של {abs(delta):g} ק\"ג):*")
            lines.append(
                f"⏱️ צפי ריאלי ובריא: כ-{weeks} שבועות (בקצב של ~0.5–0.75 ק\"ג לשבוע)"
            )
        elif delta > 0.5:
            lines.append(f"🗺️ *מפת הדרך ליעד שלך (עלייה של {delta:g} ק\"ג במסת שריר):*")
            lines.append(
                f"⏱️ צפי ריאלי ובריא: כ-{weeks} שבועות (בקצב של ~0.25–0.4 ק\"ג לשבוע)"
            )
        else:
            lines.append("🗺️ *מפת הדרך שלך לחיטוב ושמירה על המשקל:*")
            lines.append("⏱️ דגש על יציבות, שיפור הרכב הגוף וחיזוק שרירי")

        lines.append("")
        lines.append("🚩 *אבני הדרך להצלחה:*")
        icons = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
        for idx, m in enumerate(milestones):
            ico = icons[idx] if idx < len(icons) else f"{idx + 1}️⃣"
            d_str = f" ({m['delta_kg']:+g} ק\"ג)" if m.get("delta_kg") else ""
            lines.append(f"{ico} *{m['weight_kg']} ק\"ג*{d_str} — {m['description']}")

    # Daily targets
    lines.append("")
    lines.append("🔥 *יעדים יומיים מומלצים:*")
    if targets.get("calories"):
        lines.append(f"• קלוריות: *{targets['calories']:,}* קק\"ל")
    if targets.get("protein_g"):
        lines.append(f"• חלבון: *{targets['protein_g']}* גרם")
    if targets.get("water_l"):
        lines.append(
            f"• מים: *{targets['water_l']}* ליטר ({targets.get('water_cups', 10)} כוסות)"
        )
    if targets.get("weekly_workouts"):
        lines.append(f"• אימונים: *{targets['weekly_workouts']}* בשבוע")

    lines.extend(
        [
            "",
            "מעכשיו אשלח לך בכל בוקר תוכנית יומית לאוכל, שתייה ואימון.",
            "",
            "*פקודות שימושיות:*",
            "• *תפריט* — התוכנית של היום",
            "• *שתיתי 2* — תיעוד כוסות מים",
            "• *אכלתי ...* — משוב על הארוחה וספירת קלוריות",
            "• *סיימתי אימון* — סימון אימון",
            "• *סטטוס* — ההתקדמות שלך ואבני הדרך",
            "• *עזרה* — כל הפקודות",
            "",
            "קדימה, יוצאים לדרך! 💪",
        ]
    )
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    """Format a number without trailing ``.0``."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if number.is_integer():
        return str(int(number))
    return f"{number:.1f}"
