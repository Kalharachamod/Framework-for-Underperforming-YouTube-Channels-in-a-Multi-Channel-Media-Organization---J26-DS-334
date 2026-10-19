from __future__ import annotations

import unittest

import pandas as pd

from research.component_2.feasibility_experiment.supply_topics import (
    boilerplate_lines,
    build_supply_documents,
    clean_line,
    supply_distributions,
    tokenize,
)


BOILERPLATE = "Follow us on\n🔗 Facebook 👉🏼 https://www.facebook.com/tvderanaofficial\nCall 0771234567"


class SupplyDocumentTests(unittest.TestCase):
    def setUp(self):
        rows = []
        for i in range(10):
            rows.append(
                {
                    "video_id": f"v{i}",
                    "channel_name": "Dream Star",
                    "published_at": f"2025-0{1 + i % 2}-01T00:00:00Z",
                    "view_count": 100,
                    "title": f"Song {i} | Dream Star Season 12 | #DreamStar",
                    "description": f"{BOILERPLATE}\nContestant name{i} sings ගීතය {i}",
                }
            )
        self.videos = pd.DataFrame(rows)

    def test_repeated_lines_are_boilerplate(self):
        repeated = boilerplate_lines(self.videos["description"])
        self.assertIn("Follow us on", repeated)
        self.assertNotIn("Contestant name1 sings ගීතය 1", repeated)

    def test_documents_drop_boilerplate_urls_and_phones(self):
        documents = build_supply_documents(self.videos)
        text = " ".join(documents["document"])
        self.assertNotIn("facebook.com", text)
        self.assertNotIn("Follow us on", text)
        self.assertNotIn("0771234567", text)
        self.assertIn("ගීතය", text)
        self.assertIn("DreamStar", text)

    def test_crew_credits_dropped_but_on_screen_people_kept(self):
        videos = self.videos.copy()
        videos["description"] = videos["description"] + "\nDirector : Crew Person"
        # Judges vary by season; a line shared by every video would be channel boilerplate.
        videos.loc[:2, "description"] = videos.loc[:2, "description"] + "\nJudges : Keerthi Pasquel"
        text = " ".join(build_supply_documents(videos)["document"])
        self.assertNotIn("Crew Person", text)
        self.assertIn("Keerthi Pasquel", text)

    def test_clean_line_preserves_sinhala_conjuncts(self):
        self.assertEqual(clean_line("ශ්‍රී ලංකා #rugby https://x.com"), "ශ්‍රී ලංකා rugby")

    def test_tokenize_removes_brand_words_keeps_content(self):
        tokens = tokenize("TV Derana Season 12 Episode 4 | Iskole teledrama ගීතය")
        self.assertNotIn("derana", tokens)
        self.assertNotIn("season", tokens)
        self.assertIn("iskole", tokens)
        self.assertIn("ගීතය", tokens)

    def test_supply_distributions_sum_to_one(self):
        documents = build_supply_documents(self.videos)
        documents["topic"] = [0, 1, -1, 0, 1, 0, 1, 0, 1, 0]
        by_channel, by_month = supply_distributions(documents, "topic")
        self.assertAlmostEqual(float(by_channel.sum(axis=1).iloc[0]), 1.0)
        self.assertNotIn(-1, by_channel.columns)
        sums = by_month.groupby(["channel_name", "month"])["share"].sum()
        self.assertTrue(((sums - 1.0).abs() < 1e-9).all())


if __name__ == "__main__":
    unittest.main()
