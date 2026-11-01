"""Daily plan generation, validation and Hebrew message composition.

The deterministic fallback plan is important: the bot stays useful before an
AI key is configured and whenever the provider is unreachable.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .metrics import targets_for
from .text import clean_name, format_progress_bar, weekday_he

BREAKFASTS: tuple[tuple[str, int], ...] = (
    ("יוגורט יווני 2% עם 30 גרם גרנולה וחצי כוס אוכמניות", 380),
    ("חביתה משתי ביצים עם סלט ירקות ופרוסת לחם מלא", 400),
    ("שיבולת שועל (50 גרם) עם חלב, קינמון ותפוח מגורר", 360),
    ("טוסט אבוקדו על לחם מלא עם ביצה קשה", 390),
    ("קוטג' 5% עם עגבנייה, מלפפון וזיתים + פיתה מלאה", 370),
    ("שתי פנקייקס חלבון עם דבש ופירות", 410),
    ("סמוזי: בננה, חלב, שיבולת שועל וכף חמאת בוטנים", 380),
)

LUNCHES: tuple[tuple[str, int], ...] = (
    ("חזה עוף בגריל (150 ג') + אורז מלא + סלט ירקות", 550),
    ("שלמון אפוי (150 ג') + בטטה + ברוקולי", 560),
    ("קוסקוס מלא עם חומוס, ירקות צלויים וטחינה", 540),
    ("טורטייה מלאה עם טונה, ירקות וטחינה", 500),
    ("מג'דרה עדשים ואורז + סלט", 520),
    ("קציצות הודו בתנור + פירה כרובית + סלט", 530),
    ("סלט גדול עם ביצים, אבוקדו, גבינה בולגרית ולחם מלא", 480),
)

DINNERS: tuple[tuple[str, int], ...] = (
    ("חביתת ירקות + סלט + פרוסת לחם מלא", 350),
    ("טופו מוקפץ עם ירקות ואטריות אורז", 400),
    ("גבינות לבנות עם ירקות ולחם מלא", 380),
    ("מרק עדשים + פרוסת לחם מלא", 340),
    ("דג אפוי עם ירקות שורש", 380),
    ("שקשוקה קטנה עם שתי ביצים ולחם מלא", 420),
    ("סלט חומוס-ירקות עם פיתה מלאה", 390),
)

SNACKS: tuple[tuple[str, int], ...] = (
    ("תפוח + 10 שקדים", 180),
    ("יוגורט טבעי + פירות יער", 150),
    ("גזר ומלפפון עם חומוס", 160),
    ("פרוסת גבינה צהובה + עגבנייה", 140),
    ("שייק חלבון עם חלב", 170),
    ("30 גרם אגוזים + שזיף", 200),
    ("קרקר מלא עם גבינת קוטג'", 150),
)

WORKOUTS: tuple[dict[str, Any], ...] = (
    {
        "title": "אימון כוח לכל הגוף",
        "duration_min": 35,
        "intensity": "בינונית",
        "exercises": [
            {"name": "סקוואט במשקל גוף", "sets": "3", "reps": "12"},
            {"name": "שכיבות סמיכה (אפשר על ברכיים)", "sets": "3", "reps": "8–12"},
            {"name": "חתירה בגומייה או משקולת", "sets": "3", "reps": "12"},
            {"name": "פלאנק", "sets": "3", "reps": "30 שניות"},
            {"name": "הליכה קלה", "sets": "1", "reps": "10 דקות"},
        ],
    },
    {
        "title": "קרדיו בעצימות בינונית",
        "duration_min": 25,
        "intensity": "בינונית",
        "exercises": [
            {"name": "חימום הליכה", "sets": "1", "reps": "5 דקות"},
            {"name": "סבבים: דקה מהיר / דקה קל", "sets": "6", "reps": "12 דקות"},
            {"name": "קירור ומתיחות", "sets": "1", "reps": "5 דקות"},
        ],
    },
    {
        "title": "חיזוק פלג גוף תחתון",
        "duration_min": 30,
        "intensity": "בינונית",
        "exercises": [
            {"name": "לאנג'ים", "sets": "3", "reps": "10 לכל רגל"},
            {"name": "סקוואט", "sets": "3", "reps": "15"},
            {"name": "גשר ירכיים", "sets": "3", "reps": "15"},
            {"name": "עליות עקבים", "sets": "3", "reps": "20"},
        ],
    },
    {
        "title": "מוביליטי וליבה",
        "duration_min": 20,
        "intensity": "קלה",
        "exercises": [
            {"name": "מתיחות דינמיות", "sets": "1", "reps": "5 דקות"},
            {"name": "פלאנק", "sets": "3", "reps": "20–40 שניות"},
            {"name": "דד באג", "sets": "3", "reps": "10 לכל צד"},
            {"name": "גלגול גב ושחרור", "sets": "1", "reps": "5 דקות"},
        ],
    },
)

TIPS: tuple[str, ...] = (
    "שתו כוס מים לפני כל ארוחה — זה עוזר לשובע ולעיכול.",
    "הוסיפו ירקות לכל ארוחה: נפח, סיבים ותחושת שובע.",
    "הקפידו על חלבון בכל ארוחה: ביצים, עוף, דג, טופו או קטניות.",
    "10 דקות הליכה אחרי הארוחה מסייעות לעיכול ולאיזון הסוכר.",
    "שינה של 7–8 שעות משפיעה ישירות על תיאבון ואנרגיה.",
    "80% עקביות ו־20% גמישות — זה מה שמחזיק לאורך זמן.",
    "שקלו את עצמכם פעם בשבוע, באותו זמן, אחרי השירותים.",
)

CLOSINGS: tuple[str, ...] = (
    "איך מרגיש לך היום? כתבו לי מה אכלתם ואעדכן 💬",
    "בהצלחה היום! ספרו לי איך היה האימון 💪",
    "אם משהו לא מתאים — כתבו לי ואתאים את התוכנית 🙂",
    "אני כאן לכל שאלה. יום נעים! ☀️",
)


def fallback_plan(
    profile: dict[str, Any],
    day: date,
    coach_name: str = "המאמן",
) -> dict[str, Any]:
    """Build a balanced daily plan without calling an AI provider."""
    targets = targets_for(profile)
    index = day.weekday()
    goal = str(profile.get("goal") or "health")

    calories = int(targets.get("calories") or 2000)
    split = (0.25, 0.35, 0.28, 0.12)
    meal_data = (
        ("ארוחת בוקר", "08:00", BREAKFASTS[index % len(BREAKFASTS)]),
        ("ארוחת צהריים", "13:00", LUNCHES[index % len(LUNCHES)]),
        ("ארוחת ערב", "19:00", DINNERS[index % len(DINNERS)]),
        ("נשנוש", "16:30", SNACKS[index % len(SNACKS)]),
    )
    meals = []
    for share, (name, time_label, (text, _base_kcal)) in zip(
        split, meal_data, strict=True
    ):
        meals.append(
            {
                "name": name,
                "time": time_label,
                "items": [text],
                "kcal": int(round(calories * share / 10.0) * 10),
            }
        )

    workout = dict(WORKOUTS[index % len(WORKOUTS)])
    workout["exercises"] = [dict(item) for item in workout["exercises"]]

    focus = {
        "lose_weight": "גירעון קלירי + תנועה יומית",
        "build_muscle": "חלבון גבוה + אימוני כוח",
        "maintain": "איזון ואחידות לאורך השבוע",
        "health": "הרגלים קטנים ועקביים",
    }.get(goal, "הרגלים קטנים ועקביים")

    return {
        "date": day.isoformat(),
        "focus": focus,
        "meals": meals,
        "water_l": targets.get("water_l") or 2.4,
        "workout": workout,
        "tips": [TIPS[index % len(TIPS)], TIPS[(index + 3) % len(TIPS)]],
        "closing": CLOSINGS[index % len(CLOSINGS)],
        "source": "fallback",
        "coach_name": coach_name,
    }


def compose_plan_message(
    user: dict[str, Any],
    plan: dict[str, Any],
    water_times: list[str] | None = None,
) -> str:
    """Render a plan as a WhatsApp-friendly Hebrew message."""
    name = clean_name(user.get("name"))
    profile = user.get("profile") or {}
    targets = targets_for(profile)
    goal = profile.get("goal_text") or targets.get("goal_label")

    try:
        day = date.fromisoformat(str(plan.get("date")))
    except ValueError:
        day = date.today()

    lines: list[str] = [
        f"בוקר טוב {name}! ☀️",
        f"*התוכנית שלך ליום {weekday_he(day)}*",
    ]
    if goal:
        calories = targets.get("calories")
        lines.append(f"🎯 {goal}" + (f" · {calories} קק\"ל יעד" if calories else ""))
    if plan.get("focus"):
        lines.append(f"🧭 מיקוד: {plan['focus']}")
    lines.append("")

    lines.append("🍽️ *תזונה*")
    for meal in plan.get("meals") or []:
        items = meal.get("items") or []
        text = "; ".join(str(item) for item in items if item)
        kcal = meal.get("kcal")
        suffix = f" (~{kcal} קק\"ל)" if kcal else ""
        lines.append(
            f"• *{meal.get('name', 'ארוחה')}* {meal.get('time', '')}{suffix}".rstrip()
        )
        if text:
            lines.append(f"  {text}")
    lines.append("")

    water_l = plan.get("water_l") or targets.get("water_l")
    lines.append("💧 *שתייה*")
    if water_l:
        lines.append(f"יעד: {water_l} ליטר (כ־{int(round(float(water_l) * 4))} כוסות)")
    if water_times:
        lines.append(f"תזכורות: {', '.join(water_times)}")
    lines.append("כתבו *שתיתי 2* כדי לתעד כוסות.")
    lines.append("")

    workout = plan.get("workout") or {}
    if workout:
        title = workout.get("title", "אימון")
        duration = workout.get("duration_min")
        intensity = workout.get("intensity")
        header = f"🏋️ *אימון: {title}*"
        meta = " · ".join(
            part for part in (f"{duration} דק'" if duration else "", intensity or "") if part
        )
        lines.append(header)
        if meta:
            lines.append(meta)
        for exercise in workout.get("exercises") or []:
            ex_name = exercise.get("name")
            if not ex_name:
                continue
            sets = exercise.get("sets")
            reps = exercise.get("reps")
            detail = " × ".join(str(part) for part in (sets, reps) if part)
            lines.append(f"• {ex_name}" + (f" — {detail}" if detail else ""))
        lines.append("כתבו *סיימתי אימון* כשמסיימים 💪")
        lines.append("")

    tips = [str(tip) for tip in (plan.get("tips") or []) if tip]
    if tips:
        lines.append("💡 *טיפ יומי*")
        for tip in tips[:3]:
            lines.append(f"• {tip}")
        lines.append("")

    if plan.get("closing"):
        lines.append(str(plan["closing"]))

    lines.append("")
    lines.append("_הערכה כללית, לא ייעוץ רפואי. במצב רפואי — התייעצו עם רופא/דיאטן._")

    return "\n".join(lines).strip()


def compose_water_reminder(
    user: dict[str, Any],
    targets: dict[str, Any],
    done_ml: int,
    time_label: str = "",
) -> str:
    """Render a water reminder with progress."""
    name = clean_name(user.get("name"))
    target_ml = int(targets.get("water_ml") or 2500)
    bar = format_progress_bar(done_ml, target_ml)
    done_l = round(done_ml / 1000.0, 1)
    target_l = round(target_ml / 1000.0, 1)
    lines = [
        f"💧 *תזכורת שתייה* — {name}" + (f" · {time_label}" if time_label else ""),
        f"{bar}",
        f"שתיתם {done_l} מתוך {target_l} ליטר.",
        "",
        "כוס מים עכשיו? 🚰",
        'כתבו *שתיתי 1* כדי לתעד.',
    ]
    return "\n".join(lines)


def compose_workout_reminder(
    user: dict[str, Any],
    plan: dict[str, Any] | None,
    time_label: str = "",
) -> str:
    """Render a workout reminder based on today's plan."""
    name = clean_name(user.get("name"))
    workout = (plan or {}).get("workout") or {}
    title = workout.get("title") or "תנועה יומית"
    duration = workout.get("duration_min")
    lines = [
        f"🏋️ *תזכורת אימון* — {name}" + (f" · {time_label}" if time_label else ""),
        f"היום: *{title}*" + (f" ({duration} דק')" if duration else ""),
        "",
        "אפילו 15 דקות נחשבות — העיקר לזוז 💪",
        'כתבו *סיימתי אימון* בסיום.',
    ]
    return "\n".join(lines)


def normalise_plan(
    raw: Any,
    profile: dict[str, Any],
    day: date,
    coach_name: str = "המאמן",
) -> dict[str, Any]:
    """Validate an AI-produced plan and fill any gaps from the fallback."""
    fallback = fallback_plan(profile, day, coach_name)
    if not isinstance(raw, dict):
        return fallback

    plan = dict(fallback)
    if str(raw.get("date") or "") == day.isoformat():
        plan["date"] = day.isoformat()
    plan["focus"] = str(raw.get("focus") or fallback["focus"])[:120]
    plan["source"] = str(raw.get("source") or "ai")

    meals = raw.get("meals")
    cleaned_meals: list[dict[str, Any]] = []
    if isinstance(meals, list):
        for item in meals[:6]:
            if not isinstance(item, dict):
                continue
            items = item.get("items")
            if isinstance(items, str):
                items = [items]
            if not isinstance(items, list):
                items = []
            cleaned_items = [str(entry)[:160] for entry in items if str(entry).strip()]
            name = str(item.get("name") or "").strip()
            if not name or not cleaned_items:
                continue
            try:
                kcal = int(float(item.get("kcal") or 0))
            except (TypeError, ValueError):
                kcal = 0
            cleaned_meals.append(
                {
                    "name": name[:40],
                    "time": str(item.get("time") or "")[:12],
                    "items": cleaned_items[:4],
                    "kcal": max(0, min(kcal, 2500)),
                }
            )
    if len(cleaned_meals) >= 2:
        plan["meals"] = cleaned_meals

    workout = raw.get("workout")
    if isinstance(workout, dict) and workout.get("title"):
        exercises: list[dict[str, str]] = []
        raw_exercises = workout.get("exercises")
        if isinstance(raw_exercises, list):
            for exercise in raw_exercises[:10]:
                if not isinstance(exercise, dict):
                    continue
                ex_name = str(exercise.get("name") or "").strip()
                if not ex_name:
                    continue
                exercises.append(
                    {
                        "name": ex_name[:60],
                        "sets": str(exercise.get("sets") or "")[:12],
                        "reps": str(exercise.get("reps") or "")[:24],
                    }
                )
        if exercises:
            try:
                duration = int(float(workout.get("duration_min") or 0))
            except (TypeError, ValueError):
                duration = 0
            plan["workout"] = {
                "title": str(workout.get("title"))[:60],
                "duration_min": max(0, min(duration, 180)),
                "intensity": str(workout.get("intensity") or "בינונית")[:20],
                "exercises": exercises,
            }

    try:
        water_l = float(raw.get("water_l") or fallback.get("water_l") or 2.4)
    except (TypeError, ValueError):
        water_l = float(fallback.get("water_l") or 2.4)
    plan["water_l"] = round(max(1.0, min(water_l, 5.0)), 1)

    tips = raw.get("tips")
    if isinstance(tips, list):
        cleaned_tips = [str(tip)[:180] for tip in tips if str(tip).strip()]
        if cleaned_tips:
            plan["tips"] = cleaned_tips[:4]

    closing = raw.get("closing")
    if isinstance(closing, str) and closing.strip():
        plan["closing"] = closing.strip()[:220]

    plan["coach_name"] = coach_name
    return plan


def plan_public_view(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a copy of the plan safe to hand to the panel."""
    if not isinstance(plan, dict):
        return None
    return {
        "date": plan.get("date"),
        "focus": plan.get("focus"),
        "meals": plan.get("meals") or [],
        "water_l": plan.get("water_l"),
        "workout": plan.get("workout") or {},
        "tips": plan.get("tips") or [],
        "closing": plan.get("closing") or "",
        "source": plan.get("source") or "fallback",
    }
