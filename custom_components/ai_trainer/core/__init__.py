"""Pure data helpers shared by the integration, the panel and the tests.

Nothing in this package imports Home Assistant.  That keeps the business
logic trivially testable and makes it safe to reuse from tools.
"""

from __future__ import annotations

from .metrics import (
    build_weight_plan,
    calculate_bmi,
    goal_label,
    healthy_weight_range,
    targets_for,
)
from .models import new_profile, new_user, normalize_phone
from .onboarding import (
    NEXT_QUESTION,
    apply_onboarding_answer,
    onboarding_summary,
    start_onboarding,
)
from .plan import (
    compose_plan_message,
    compose_water_reminder,
    compose_workout_reminder,
    fallback_plan,
    normalise_plan,
)
from .text import (
    NON_WATER_DRINKS,
    detect_command,
    format_progress_bar,
    is_affirmative,
    is_negative,
    is_question,
    is_water_decrease,
    normalise_hebrew,
    parse_age_or_dob,
    parse_calories_entry,
    parse_goal,
    parse_height_cm,
    parse_sex,
    parse_water_cups,
    parse_weight_kg,
    weekday_he,
)

__all__ = [
    "NEXT_QUESTION",
    "NON_WATER_DRINKS",
    "apply_onboarding_answer",
    "build_weight_plan",
    "calculate_bmi",
    "compose_plan_message",
    "compose_water_reminder",
    "compose_workout_reminder",
    "detect_command",
    "fallback_plan",
    "format_progress_bar",
    "goal_label",
    "healthy_weight_range",
    "is_affirmative",
    "is_negative",
    "is_question",
    "is_water_decrease",
    "new_profile",
    "new_user",
    "normalise_plan",
    "normalise_hebrew",
    "normalize_phone",
    "onboarding_summary",
    "parse_age_or_dob",
    "parse_calories_entry",
    "parse_goal",
    "parse_height_cm",
    "parse_sex",
    "parse_water_cups",
    "parse_weight_kg",
    "start_onboarding",
    "targets_for",
    "weekday_he",
]
