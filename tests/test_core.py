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
from core.prompts import calorie_analysis_prompt, chat_messages  # noqa: E402
from core.text import (  # noqa: E402
    detect_command,
    format_progress_bar,
    is_affirmative,
    is_negative,
    is_question,
    is_water_decrease,
    parse_calories_entry,
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
        self.assertEqual(detect_command("קלוריות"), "calories")
        self.assertEqual(detect_command("כמה אכלתי"), "calories")
        self.assertEqual(detect_command("calories"), "calories")
        self.assertEqual(detect_command("שתתי 1.5 ליטר מים"), "water")
        self.assertEqual(detect_command("תוריד את 2 כוסות אחרונות. זה תיוג לא נכון"), "water_decrease")
        self.assertEqual(detect_command("תוריד 2 כוסות"), "water_decrease")
        self.assertEqual(detect_command("תמחק כוס מים"), "water_decrease")
        self.assertEqual(detect_command("מחק"), "delete")
        self.assertIsNone(detect_command("מה שלומך?"))
        self.assertIsNone(detect_command("כוס אספרסו נכנס תחת מים?"))
        self.assertIsNone(detect_command("שתתי כוס אספרסו עם נגיעה חלב סויה וניל"))
        self.assertIsNone(detect_command("שתיתי כוס קפה"))
        self.assertIsNone(detect_command("שתתי שייק חלבון"))
        self.assertIsNone(
            detect_command(
                "מצטער, ספק ה-AI לא זמין כרגע 🙏\n"
                "אפשר לכתוב תפריט לתוכנית הבסיסית, שתיתי, סיימתי אימון או סטטוס."
            )
        )
        self.assertIsNone(detect_command("לא סיימתי אימון היום"))
        self.assertIsNone(
            detect_command(
                "כלתי היום בצהריים חצי מנה שווארמה עם צלוחית חציל מטוגן. "
                "בבוקר שתתי משקה פרו 20 גרם חלבון. וכוס אספרסו עם חלב סויה בטעם וניל."
            )
        )
        self.assertIsNone(
            detect_command(
                "אכלתי היום בצהריים חצי מנה שווארמה עם צלוחית חציל מטוגן. "
                "בבוקר שתתי משקה פרו 20 גרם חלבון. וכוס אספרסו עם חלב סויה בטעם וניל."
            )
        )
        self.assertEqual(detect_command("סיימתי אימון היום"), "workout_done")
        self.assertEqual(detect_command("סיימתי אימון 💪"), "workout_done")
        self.assertEqual(detect_command("אימון בוצע!"), "workout_done")
        self.assertEqual(detect_command("עשיתי אימון"), "workout_done")
        self.assertEqual(detect_command("התאמנתי"), "workout_done")

    def test_questions(self):
        self.assertTrue(is_question("כוס אספרסו נכנס תחת מים?"))
        self.assertTrue(is_question("כוס אספרסו נכנס תחת מים"))
        self.assertTrue(is_question("האם מותר לשתות קפה?"))
        self.assertTrue(is_question("האם אספרסו זה מים"))
        self.assertTrue(is_question("מה זה קלוריות"))
        self.assertTrue(is_question("איך להוריד במשקל"))
        self.assertFalse(is_question("שתיתי 2 כוסות מים"))
        self.assertFalse(is_question("תוריד את 2 כוסות אחרונות"))

    def test_water_decrease(self):
        self.assertTrue(is_water_decrease("תוריד את 2 כוסות אחרונות. זה תיוג לא נכון"))
        self.assertTrue(is_water_decrease("תוריד 2 כוסות"))
        self.assertTrue(is_water_decrease("תמחק כוס אחת"))
        self.assertTrue(is_water_decrease("טעות, תוריד כוס"))
        self.assertTrue(is_water_decrease("מינוס כוס"))
        self.assertFalse(is_water_decrease("שתיתי 2 כוסות מים"))

    def test_parse_water_cups_empty_or_words(self):
        self.assertEqual(parse_water_cups("כוס"), 1.0)
        self.assertEqual(parse_water_cups("בקבוק"), 2.0)
        self.assertIsNone(parse_water_cups("סתם טקסט בלי שום כמות"))

    def test_meal_log_is_conversational(self):
        self.assertIsNone(detect_command("אכלתי חביתה עם 2 כוסות מים"))

    def test_affirmative_negative(self):
        self.assertTrue(is_affirmative("כן"))
        self.assertTrue(is_affirmative("כן!"))
        self.assertTrue(is_affirmative("כן תודה"))
        self.assertTrue(is_affirmative("כן תוסיף"))
        self.assertTrue(is_affirmative("תוסיף"))
        self.assertTrue(is_affirmative("סבבה"))
        self.assertTrue(is_affirmative("בטח"))
        self.assertTrue(is_affirmative("👍"))
        self.assertTrue(is_affirmative("yes"))
        self.assertFalse(is_affirmative("לא"))
        self.assertFalse(is_affirmative("שלום"))

        self.assertTrue(is_negative("לא"))
        self.assertTrue(is_negative("לא!"))
        self.assertTrue(is_negative("לא תודה"))
        self.assertTrue(is_negative("ביטול"))
        self.assertTrue(is_negative("אל תוסיף"))
        self.assertTrue(is_negative("👎"))
        self.assertTrue(is_negative("no"))
        self.assertFalse(is_negative("כן"))

    def test_parse_calories_entry(self):
        kcal, item, is_drink = parse_calories_entry("הוסף 400 קלוריות")
        self.assertEqual(kcal, 400)
        self.assertFalse(is_drink)

        kcal, item, is_drink = parse_calories_entry("הוסף 250 קלוריות שייק חלבון")
        self.assertEqual(kcal, 250)
        self.assertTrue(is_drink)

        kcal, item, is_drink = parse_calories_entry("אכלתי שקשוקה 450 קלוריות")
        self.assertEqual(kcal, 450)
        self.assertEqual(item, "שקשוקה")

        kcal, item, is_drink = parse_calories_entry("שתיתי קפה 80 קק\"ל")
        self.assertEqual(kcal, 80)
        self.assertTrue(is_drink)

        kcal, item, is_drink = parse_calories_entry("300 קלוריות")
        self.assertEqual(kcal, 300)

        self.assertIsNone(parse_calories_entry("מה נשמע?")[0])

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
        self.assertIsNone(user["pending_calorie_add"])
        self.assertEqual(user["stats"]["calories_today"], 0)
        self.assertEqual(user["stats"]["food_log"], [])

    def test_ensure_user_shape(self):
        user = {"phone": "972501234567", "profile": {"weight_kg": 80}}
        ensure_user_shape(user, "today", "now")
        self.assertEqual(user["profile"]["weight_kg"], 80)
        self.assertIn("height_cm", user["profile"])
        self.assertEqual(user["reminders"], {"daily": None, "water": None, "workout": None})
        self.assertEqual(user["stats"]["water_ml_today"], 0)
        self.assertEqual(user["stats"]["calories_today"], 0)
        self.assertIn("food_log", user["stats"])
        self.assertIn("pending_calorie_add", user)


class CaloriePromptTests(unittest.TestCase):
    def test_calorie_prompt_structure(self):
        user = make_user(weight_kg=75, height_cm=175)
        system, prompt = calorie_analysis_prompt(user, caption="סלט יווני וקפה")
        self.assertIn("דיאטן", system)
        self.assertIn("JSON", system)
        self.assertIn("דני", prompt)
        self.assertIn("סלט יווני וקפה", prompt)
        self.assertIn("is_drink", prompt)

    def test_chat_messages_alternation(self):
        user = make_user(weight_kg=75, height_cm=175)
        # History with consecutive user turns, leading assistant turn, etc.
        history = [
            {"role": "assistant", "content": "ברוך הבא"},
            {"role": "user", "content": "הודעה 1"},
            {"role": "user", "content": "הודעה 2"},
            {"role": "assistant", "content": "תשובה 1"},
            {"role": "assistant", "content": "תשובה 2"},
        ]
        system, messages = chat_messages({}, user, None, history, "הודעה 3")
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[-1]["role"], "user")
        # Check strict alternation
        for i in range(len(messages) - 1):
            self.assertNotEqual(messages[i]["role"], messages[i + 1]["role"])


if __name__ == "__main__":
    unittest.main()
