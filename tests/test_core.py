"""Tests for the pure-Python core of the AI Trainer integration.

These tests deliberately avoid importing Home Assistant: the integration
package ``custom_components/ai_trainer`` imports ``homeassistant`` at module
level, so the core directory is added to ``sys.path`` directly.

Run with::

    python -m unittest discover -s tests -v
    # or, when pytest is installed
    python -m pytest tests -q
"""

from __future__ import annotations

import re
import sys
import unittest
from datetime import date
from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "ai_trainer"
if str(INTEGRATION_DIR) not in sys.path:
    sys.path.insert(0, str(INTEGRATION_DIR))

from core.metrics import calculate_bmi, targets_for  # noqa: E402
from core.models import ensure_user_shape, new_user, normalize_phone  # noqa: E402
from core.onboarding import apply_onboarding_answer, start_onboarding  # noqa: E402
from core.plan import (  # noqa: E402
    compose_plan_message,
    compose_water_reminder,
    compose_workout_reminder,
    fallback_plan,
    normalise_plan,
    plan_public_view,
)
from core.text import (  # noqa: E402
    detect_command,
    format_progress_bar,
    parse_goal,
    parse_height_cm,
    parse_water_cups,
    parse_weight_kg,
    split_message,
    weekday_he,
)

TODAY = date(2026, 11, 1)  # Sunday


def make_user(**profile):
    user = new_user("972501234567", "972501234567@s.whatsapp.net", "דני", "2026-11-01T08:00:00", "2026-11-01")
    user["profile"].update(profile)
    return user


class PhoneTests(unittest.TestCase):
    def test_strips_jid_and_symbols(self):
        self.assertEqual(normalize_phone("972-50-123-4567@s.whatsapp.net"), "972501234567")
        self.assertEqual(normalize_phone("+972 50 123 4567"), "972501234567")

    def test_double_zero_prefix(self):
        self.assertEqual(normalize_phone("00972501234567"), "972501234567")

    def test_empty(self):
        self.assertEqual(normalize_phone(None), "")


class ParsingTests(unittest.TestCase):
    def test_weight_kilograms(self):
        self.assertEqual(parse_weight_kg("78.5"), 78.5)
        self.assertEqual(parse_weight_kg("78,5 קילו"), 78.5)
        self.assertEqual(parse_weight_kg("המשקל שלי 80"), 80.0)

    def test_weight_pounds(self):
        self.assertAlmostEqual(parse_weight_kg("176 lbs"), 79.8, places=1)

    def test_weight_out_of_range(self):
        self.assertIsNone(parse_weight_kg("500"))
        self.assertIsNone(parse_weight_kg("abc"))

    def test_height_centimetres(self):
        self.assertEqual(parse_height_cm("175"), 175)
        self.assertEqual(parse_height_cm("1.75"), 175)
        self.assertEqual(parse_height_cm('5\'9"'), 175)

    def test_height_out_of_range(self):
        self.assertIsNone(parse_height_cm("60"))
        self.assertIsNone(parse_height_cm(""))

    def test_water_cups(self):
        self.assertEqual(parse_water_cups("2"), 2.0)
        self.assertEqual(parse_water_cups("שתיתי 3"), 3.0)
        self.assertEqual(parse_water_cups("1.5 ליטר"), 6.0)
        self.assertEqual(parse_water_cups("500 מ\"ל"), 2.0)
        self.assertEqual(parse_water_cups("חצי"), 0.5)

    def test_water_rejects_too_much(self):
        self.assertIsNone(parse_water_cups("20"))

    def test_goal_numbers(self):
        self.assertEqual(parse_goal("1")[0], "lose_weight")
        self.assertEqual(parse_goal("2")[0], "build_muscle")
        self.assertEqual(parse_goal("3")[0], "maintain")
        self.assertEqual(parse_goal("4")[0], "health")

    def test_goal_keywords(self):
        self.assertEqual(parse_goal("אני רוצה לרדת 5 קילו")[0], "lose_weight")
        self.assertEqual(parse_goal("לבנות שריר")[0], "build_muscle")
        self.assertEqual(parse_goal("maintain weight")[0], "maintain")

    def test_goal_free_text(self):
        goal, text = parse_goal("להרגיש טוב יותר באנרגיה יומיומית")
        self.assertEqual(goal, "health")
        self.assertEqual(text, "להרגיש טוב יותר באנרגיה יומיומית")

    def test_commands(self):
        self.assertEqual(detect_command("תפריט"), "plan")
        self.assertEqual(detect_command("שתיתי 2"), "water")
        self.assertEqual(detect_command("סיימתי אימון"), "workout_done")
        self.assertEqual(detect_command("עצור"), "pause")
        self.assertEqual(detect_command("הפעל"), "resume")
        self.assertEqual(detect_command("איפוס"), "reset")
        self.assertEqual(detect_command("ביטול"), "cancel")
        self.assertEqual(detect_command("סטטוס"), "status")
        self.assertIsNone(detect_command("מה שלומך?"))

    def test_meal_log_is_conversational(self):
        self.assertIsNone(detect_command("אכלתי חביתה עם 2 כוסות מים"))

    def test_progress_bar(self):
        self.assertEqual(format_progress_bar(5, 10), "▰▰▰▰▰▱▱▱▱▱ 50%")
        self.assertEqual(format_progress_bar(0, 10), "▱▱▱▱▱▱▱▱▱▱ 0%")
        self.assertEqual(format_progress_bar(10, 10), "▰▰▰▰▰▰▰▰▰▰ 100%")
        self.assertEqual(format_progress_bar(1, 0), "")

    def test_weekday_hebrew(self):
        self.assertEqual(weekday_he(date(2026, 11, 1)), "ראשון")
        self.assertEqual(weekday_he(date(2026, 11, 6)), "שישי")


class SplitMessageTests(unittest.TestCase):
    def test_short_message_is_single_chunk(self):
        self.assertEqual(split_message("שלום"), ["שלום"])
        self.assertEqual(split_message("   "), [])

    def test_splits_on_lines(self):
        text = "\n".join(["שורה" * 10] * 40)
        chunks = split_message(text, limit=120)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 120 for chunk in chunks))
        # Only whitespace at chunk boundaries may be dropped.
        self.assertEqual(
            re.sub(r"\s+", "", "".join(chunks)), re.sub(r"\s+", "", text)
        )

    def test_hard_splits_long_line(self):
        chunks = split_message("א" * 500, limit=100)
        self.assertEqual([len(chunk) for chunk in chunks], [100] * 5)


class MetricsTests(unittest.TestCase):
    def test_bmi(self):
        self.assertEqual(calculate_bmi(80, 180), 24.7)
        self.assertIsNone(calculate_bmi(None, 180))
        self.assertIsNone(calculate_bmi(80, 0))

    def test_targets_shape(self):
        targets = targets_for({"weight_kg": 80, "height_cm": 180, "goal": "lose_weight"})
        self.assertEqual(targets["bmi"], 24.7)
        self.assertEqual(targets["bmi_category"], "משקל תקין")
        self.assertGreaterEqual(targets["calories"], 1400)
        self.assertGreater(targets["protein_g"], 0)
        self.assertGreater(targets["water_ml"], 0)

    def test_targets_incomplete_profile(self):
        targets = targets_for({})
        self.assertIsNone(targets["bmi"])
        self.assertIsNone(targets["calories"])
        self.assertEqual(targets["goal_label"], "אורח חיים בריא")


class OnboardingTests(unittest.TestCase):
    def test_full_flow(self):
        user = new_user("972501234567", "", "דני", "2026-11-01T08:00:00", "2026-11-01")
        welcome = start_onboarding(user, "המאמן")
        self.assertIn("המאמן", welcome)
        self.assertEqual(user["onboarding_step"], "goal")

        result = apply_onboarding_answer(user, "1")
        self.assertEqual(result["step"], "weight")
        self.assertEqual(user["profile"]["goal"], "lose_weight")

        result = apply_onboarding_answer(user, "82.5")
        self.assertEqual(result["step"], "height")
        self.assertEqual(user["profile"]["weight_kg"], 82.5)
        self.assertEqual(user["profile"]["start_weight_kg"], 82.5)

        result = apply_onboarding_answer(user, "1.80")
        self.assertTrue(result["completed"])
        self.assertEqual(user["profile"]["height_cm"], 180)
        self.assertEqual(user["status"], "active")
        self.assertIn("BMI", result["reply"])

    def test_free_text_goal_is_kept(self):
        user = new_user("972501234567", "", "", "x", "y")
        result = apply_onboarding_answer(user, "בא לי להרגיש אנרגטי")
        self.assertFalse(result["completed"])
        self.assertEqual(user["profile"]["goal"], "health")
        self.assertIn("אנרגטי", user["profile"]["goal_text"])

    def test_invalid_weight_keeps_step(self):
        user = new_user("972501234567", "", "", "x", "y")
        user["onboarding_step"] = "weight"
        result = apply_onboarding_answer(user, "כבד מאוד")
        self.assertTrue(result["error"])
        self.assertEqual(user["onboarding_step"], "weight")

    def test_one_word_goal_rejected(self):
        user = new_user("972501234567", "", "", "x", "y")
        result = apply_onboarding_answer(user, "9")
        self.assertTrue(result["error"])


class PlanTests(unittest.TestCase):
    def test_fallback_plan_structure(self):
        user = make_user(weight_kg=80, height_cm=180, goal="lose_weight")
        plan = fallback_plan(user["profile"], TODAY, "המאמן")
        self.assertEqual(plan["date"], "2026-11-01")
        self.assertEqual(plan["source"], "fallback")
        self.assertEqual(len(plan["meals"]), 4)
        self.assertTrue(plan["workout"]["exercises"])
        self.assertEqual(plan["coach_name"], "המאמן")

    def test_compose_message_contains_sections(self):
        user = make_user(weight_kg=80, height_cm=180, goal="lose_weight")
        plan = fallback_plan(user["profile"], TODAY)
        text = compose_plan_message(user, plan, ["10:00", "13:00"])
        self.assertIn("בוקר טוב דני", text)
        self.assertIn("תזונה", text)
        self.assertIn("שתייה", text)
        self.assertIn("אימון", text)
        self.assertIn("10:00", text)
        self.assertIn("לא ייעוץ רפואי", text)

    def test_compose_without_calories(self):
        user = make_user()
        plan = fallback_plan(user["profile"], TODAY)
        text = compose_plan_message(user, plan)
        self.assertNotIn("None", text)
        self.assertNotIn("קק\"ל יעד", text)

    def test_water_and_workout_reminders(self):
        user = make_user(weight_kg=80, height_cm=180)
        targets = targets_for(user["profile"])
        water = compose_water_reminder(user, targets, 1000, "13:00")
        self.assertIn("13:00", water)
        self.assertIn("1.0", water)
        workout = compose_workout_reminder(user, fallback_plan(user["profile"], TODAY), "18:00")
        self.assertIn("18:00", workout)

    def test_normalise_plan_fills_gaps(self):
        user = make_user(weight_kg=80, height_cm=180, goal="health")
        raw = {
            "focus": "   ",
            "meals": [{"name": "ארוחה", "items": "משהו", "kcal": "600"}],
            "water_l": 99,
            "workout": {"title": "אימון", "exercises": [{"name": "סקוואט"}]},
            "tips": ["טיפ"],
            "closing": "  בהצלחה  ",
        }
        plan = normalise_plan(raw, user["profile"], TODAY)
        self.assertEqual(plan["source"], "ai")
        self.assertEqual(len(plan["meals"]), 4)  # fallback kept (only one valid meal)
        self.assertEqual(plan["water_l"], 5.0)
        self.assertEqual(plan["closing"], "בהצלחה")
        self.assertEqual(plan["tips"], ["טיפ"])

    def test_normalise_plan_rejects_garbage(self):
        user = make_user(weight_kg=80, height_cm=180)
        plan = normalise_plan("not a plan", user["profile"], TODAY)
        self.assertEqual(plan["source"], "fallback")

    def test_public_view(self):
        user = make_user(weight_kg=80, height_cm=180)
        view = plan_public_view(fallback_plan(user["profile"], TODAY))
        self.assertIsNotNone(view)
        self.assertEqual(view["date"], "2026-11-01")
        self.assertNotIn("coach_name", view)
        self.assertIsNone(plan_public_view(None))


class ModelTests(unittest.TestCase):
    def test_new_user_defaults(self):
        user = new_user("+972 50-123-4567", "", "  דני  ", "now", "today")
        self.assertEqual(user["id"], "972501234567")
        self.assertEqual(user["name"], "דני")
        self.assertEqual(user["status"], "onboarding")
        self.assertEqual(user["onboarding_step"], "goal")
        self.assertFalse(user["pending_reset"])

    def test_ensure_user_shape(self):
        user = {"phone": "972501234567", "profile": {"weight_kg": 80}}
        ensure_user_shape(user, "today", "now")
        self.assertEqual(user["profile"]["weight_kg"], 80)
        self.assertIn("height_cm", user["profile"])
        self.assertEqual(user["reminders"], {"daily": None, "water": None, "workout": None})
        self.assertEqual(user["stats"]["water_ml_today"], 0)


if __name__ == "__main__":
    unittest.main()
