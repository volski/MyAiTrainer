"""Body metrics and daily targets.

The numbers are deliberately conservative estimates, not medical advice.
They give the AI a stable baseline and let the bot produce a useful plan even
when no AI provider is configured.
"""

from __future__ import annotations

from typing import Any

GOAL_LABELS: dict[str, str] = {
    "lose_weight": "ירידה במשקל",
    "build_muscle": "בניית שריר",
    "maintain": "שמירה על המשקל",
    "health": "אורח חיים בריא",
}

ACTIVITY_LABELS: dict[str, str] = {
    "low": "פעילות נמוכה",
    "moderate": "פעילות בינונית",
    "high": "פעילות גבוהה",
}

ACTIVITY_FACTORS: dict[str, float] = {
    "low": 1.2,
    "moderate": 1.375,
    "high": 1.55,
}

SEX_ADJUSTMENT: dict[str, float] = {
    "male": 5.0,
    "female": -161.0,
    "unspecified": -78.0,
}

PROTEIN_PER_KG: dict[str, float] = {
    "lose_weight": 1.8,
    "build_muscle": 1.8,
    "maintain": 1.4,
    "health": 1.4,
}

STEP_TARGETS: dict[str, int] = {
    "lose_weight": 9000,
    "build_muscle": 8000,
    "maintain": 8000,
    "health": 8000,
}

WORKOUT_TARGETS: dict[str, int] = {
    "lose_weight": 4,
    "build_muscle": 4,
    "maintain": 3,
    "health": 3,
}


def goal_label(goal: str | None) -> str:
    """Return the Hebrew label for a goal key."""
    return GOAL_LABELS.get(str(goal or ""), "אורח חיים בריא")


def activity_label(level: str | None) -> str:
    """Return the Hebrew label for an activity level."""
    return ACTIVITY_LABELS.get(str(level or ""), ACTIVITY_LABELS["moderate"])


def calculate_bmi(weight_kg: float | None, height_cm: float | None) -> float | None:
    """Return BMI rounded to one decimal, or ``None`` when data is missing."""
    if not weight_kg or not height_cm:
        return None
    height_m = float(height_cm) / 100.0
    if height_m <= 0:
        return None
    return round(float(weight_kg) / (height_m * height_m), 1)


def bmi_category(bmi: float | None) -> tuple[str, str]:
    """Return ``(hebrew_label, ui_colour)`` for a BMI value."""
    if bmi is None:
        return "לא ידוע", "neutral"
    if bmi < 18.5:
        return "תת־משקל", "amber"
    if bmi < 25:
        return "משקל תקין", "green"
    if bmi < 30:
        return "עודף משקל קל", "amber"
    return "השמנה", "red"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _round_to(value: float, step: int) -> int:
    return int(round(value / step) * step)


def healthy_weight_range(height_cm: float | None) -> tuple[float, float] | None:
    """Return healthy weight range (min_kg, max_kg) based on standard BMI 18.5 - 24.9."""
    if not height_cm or height_cm <= 0:
        return None
    h_m = float(height_cm) / 100.0
    min_w = round(18.5 * h_m * h_m, 1)
    max_w = round(24.9 * h_m * h_m, 1)
    return (min_w, max_w)


def build_weight_plan(
    current_weight: float | None,
    target_weight: float | None,
    height_cm: float | None,
    sex: str = "unspecified",
    age: int = 30,
    goal: str = "lose_weight",
) -> dict[str, Any]:
    """Generate a realistic milestones-based roadmap to arrive at the target weight."""
    if not current_weight:
        return {}

    target = target_weight if target_weight else current_weight
    delta = round(target - current_weight, 1)

    h_range = healthy_weight_range(height_cm)
    curr_bmi = calculate_bmi(current_weight, height_cm)
    target_bmi = calculate_bmi(target, height_cm)

    if delta <= -0.5:
        direction = "lose"
        abs_delta = abs(delta)
        # Safe sustainable rate: ~0.5 - 0.75 kg/week
        rate = 0.6
        weeks = max(2, int(round(abs_delta / rate)))

        if abs_delta <= 3.0:
            count = 2
        elif abs_delta <= 8.0:
            count = 3
        else:
            count = 4

        step_kg = abs_delta / count
        milestones = []
        if count == 2:
            descriptions = [
                "הקניית הרגלי שתייה, סדר בארוחות והורדת נוזלים ראשונית",
                "הגעה למשקל היעד, חגיגת ההישג ומעבר לשלב השמירה (Maintenance)",
            ]
        elif count == 3:
            descriptions = [
                "ירידה ראשונית, הסדרת זמני ארוחות והקפדה על שתיית מים",
                "הגברת שריפת שומן, שימור שריר באימונים ושיפור אנרגיה",
                "הגעה למשקל היעד וייצוב ההישג לטווח ארוך",
            ]
        else:
            descriptions = [
                "הרגלי שתייה, סדר בארוחות, גירעון קלורי מתון והורדת נוזלים ראשונית",
                "נקודת האמצע! שמירה על מסת שריר בעזרת אימוני כוח והתמדה בתפריט",
                "הישורת האחרונה, הגברת צעדים יומית ודיוק בכמויות החלבון",
                "הגעה למשקל היעד, חגיגת ההישג ומעבר לשלב השמירה (Maintenance)",
            ]

        for i in range(1, count + 1):
            if i == count:
                m_weight = target
                m_delta = delta
            else:
                m_loss = round(i * step_kg, 1)
                m_weight = round(current_weight - m_loss, 1)
                m_delta = round(-m_loss, 1)
            milestones.append(
                {
                    "step": i,
                    "weight_kg": m_weight,
                    "delta_kg": m_delta,
                    "title": f"אבן דרך {i}",
                    "description": descriptions[i - 1],
                }
            )

    elif delta >= 0.5:
        direction = "gain"
        abs_delta = delta
        # Safe muscle gain rate: ~0.25 - 0.35 kg/week
        rate = 0.3
        weeks = max(2, int(round(abs_delta / rate)))
        count = 2 if abs_delta <= 4.0 else 3
        step_kg = abs_delta / count
        descriptions = [
            "הגעה לעודף קלורי איכותי, 1.6–2.0 גרם חלבון לק\"ג ואימוני כוח עקביים",
            "עלייה נקייה במסת השריר ועומס יסף הדרגתי באימונים",
            "הגעה למשקל היעד עם שיפור משמעותי במבנה הגוף ובכוח",
        ]
        milestones = []
        for i in range(1, count + 1):
            if i == count:
                m_weight = target
                m_delta = delta
            else:
                m_gain = round(i * step_kg, 1)
                m_weight = round(current_weight + m_gain, 1)
                m_delta = round(m_gain, 1)
            milestones.append(
                {
                    "step": i,
                    "weight_kg": m_weight,
                    "delta_kg": m_delta,
                    "title": f"אבן דרך {i}",
                    "description": descriptions[i - 1],
                }
            )

    else:
        direction = "maintain"
        weeks = 4
        milestones = [
            {
                "step": 1,
                "weight_kg": current_weight,
                "delta_kg": 0.0,
                "title": "ייצוב והרגלים",
                "description": "איזון קלורי ניטרלי, שתיית מים מלאה ו-3 אימונים שבועיים",
            },
            {
                "step": 2,
                "weight_kg": current_weight,
                "delta_kg": 0.0,
                "title": "חיטוב וחיזוק (Recomposition)",
                "description": "הפחתת אחוזי שומן והעלאת טונוס שרירי תוך שמירה על המשקל",
            },
        ]

    return {
        "current_weight": current_weight,
        "target_weight": target,
        "delta_kg": delta,
        "direction": direction,
        "estimated_weeks": weeks,
        "current_bmi": curr_bmi,
        "target_bmi": target_bmi,
        "healthy_weight_min": h_range[0] if h_range else None,
        "healthy_weight_max": h_range[1] if h_range else None,
        "milestones": milestones,
    }


def targets_for(profile: dict[str, Any]) -> dict[str, Any]:
    """Compute BMI, energy, protein, water and activity targets.

    Missing weight/height yields a partial result with ``None`` values so the
    panel can render a friendly "not set" state.
    """
    weight = _as_float(profile.get("weight_kg"))
    height = _as_float(profile.get("height_cm"))
    age = _as_float(profile.get("age")) or 30.0
    sex = str(profile.get("sex") or "unspecified")
    activity = str(profile.get("activity_level") or "moderate")
    goal = str(profile.get("goal") or "health")

    bmi = calculate_bmi(weight, height)
    category, colour = bmi_category(bmi)

    result: dict[str, Any] = {
        "bmi": bmi,
        "bmi_category": category,
        "bmi_color": colour,
        "goal": goal,
        "goal_label": goal_label(goal),
        "activity": activity,
        "activity_label": activity_label(activity),
        "target_weight_kg": _as_float(profile.get("target_weight_kg")),
        "target_bmi": calculate_bmi(_as_float(profile.get("target_weight_kg")), height),
        "healthy_weight_min": healthy_weight_range(height)[0] if healthy_weight_range(height) else None,
        "healthy_weight_max": healthy_weight_range(height)[1] if healthy_weight_range(height) else None,
        "bmr": None,
        "tdee": None,
        "calories": None,
        "protein_g": None,
        "water_ml": None,
        "water_l": None,
        "water_cups": None,
        "steps": STEP_TARGETS.get(goal, 8000),
        "weekly_workouts": WORKOUT_TARGETS.get(goal, 3),
    }

    if weight is None or height is None:
        return result

    factor = ACTIVITY_FACTORS.get(activity, ACTIVITY_FACTORS["moderate"])
    sex_adjust = SEX_ADJUSTMENT.get(sex, SEX_ADJUSTMENT["unspecified"])
    bmr = 10.0 * weight + 6.25 * height - 5.0 * age + sex_adjust
    tdee = bmr * factor

    if goal == "lose_weight":
        calories = max(1400.0, tdee - 400.0)
    elif goal == "build_muscle":
        calories = tdee + 300.0
    else:
        calories = tdee
    calories = _round_to(_clamp(calories, 1200.0, 4500.0), 50)

    protein = weight * PROTEIN_PER_KG.get(goal, 1.4)
    protein_g = int(_round_to(_clamp(protein, 50.0, 220.0), 5))

    water_ml = int(_round_to(_clamp(weight * 35.0, 1500.0, 4000.0), 100))
    water_cups = int(round(water_ml / 250.0))

    result.update(
        {
            "bmr": int(round(bmr)),
            "tdee": int(round(tdee)),
            "calories": calories,
            "protein_g": protein_g,
            "water_ml": water_ml,
            "water_l": round(water_ml / 1000.0, 1),
            "water_cups": water_cups,
        }
    )
    return result


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
