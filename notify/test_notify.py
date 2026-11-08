import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ["HOUSEHOLD_CONFIG"] = str(HERE.parent / "examples" / "household.example.toml")
import household  # noqa: E402
import notify  # noqa: E402


class Split(unittest.TestCase):
    def check(self, parts, limit=notify.DISCORD_LIMIT):
        for p in parts:
            self.assertLessEqual(len(p), limit, p[:80])
            self.assertTrue(p.startswith(notify.URGENT_PREFIX))
            self.assertEqual(p.count("```") % 2, 0, "unbalanced fence")

    def test_short_single(self):
        self.assertEqual(notify.urgent_parts("hi"), ["🚨 hi"])

    def test_exactly_limit_single(self):
        body = "x" * (notify.DISCORD_LIMIT - 2)
        parts = notify.urgent_parts(body)
        self.assertEqual(len(parts), 1)
        self.assertEqual(len(parts[0]), notify.DISCORD_LIMIT)

    def test_lines_split_on_newline_no_loss(self):
        lines = [f"- device {i}: **{i % 10}%**" for i in range(300)]
        parts = notify.urgent_parts("\n".join(lines))
        self.assertGreater(len(parts), 1)
        self.check(parts)
        self.assertTrue(parts[0].endswith(f"(1/{len(parts)})"))
        joined = "\n".join(p[2:].rsplit(" (", 1)[0] for p in parts)
        self.assertEqual(joined.split("\n"), lines)

    def test_code_fence_reopened(self):
        text = "Log:\n```python\n" + "\n".join(f"x{i} = {i}" for i in range(600)) + "\n```\nend"
        parts = notify.urgent_parts(text)
        self.check(parts)
        self.assertTrue(parts[1].startswith("🚨 ```python\n"))

    def test_one_giant_word(self):
        self.check(notify.urgent_parts("a" * 5000))

    def test_shortcode_and_duplicate(self):
        self.assertEqual(notify.urgent_text(":rotating_light: x"), "🚨 x")
        self.assertEqual(notify.urgent_text("🚨 🚨x"), "🚨 x")
        self.assertEqual(notify.urgent_text("🚨:rotating_light: x"), "🚨 x")
        self.assertEqual(notify.urgent_text("🚨x"), "🚨 x")


class Config(unittest.TestCase):
    def test_lookup(self):
        self.assertEqual(household.mention("Alice"), "<@111111111111111111>")
        self.assertEqual(household.person_for_discord_id("444444444444444444"), "alice")
        self.assertEqual(household.thread("bob-reminders"),
                         ("333333333333333333", "555555555555555555"))

    def test_unknown_person(self):
        with self.assertRaises(household.ConfigError):
            notify.urgent_dm("carol", "x", dry_run=True)


if __name__ == "__main__":
    unittest.main()
