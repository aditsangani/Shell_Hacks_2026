"""Regression checks for the combined evidence pool; no network calls."""

import unittest
import hashlib
from datetime import date, timedelta

import news


class CombinedEvidenceTests(unittest.TestCase):
    event = date(2026, 9, 25)

    @staticmethod
    def article(source: str, index: int, headline: str | None = None) -> dict:
        unique = hashlib.sha256(f"{source}-{index}".encode()).hexdigest()
        return {
            "headline": headline or f"Nvidia {source} {unique}",
            "pub_date": f"2026-09-{20 + index % 6:02d}T14:00:00+00:00",
            "url": f"https://example.com/{source}/{index}",
            "snippet": "Nvidia quarterly evidence",
            "source": source,
            "publisher": source.upper(),
        }

    def test_combined_pool_enforces_total_and_source_caps(self):
        items = [self.article(source, i) for source in ("nyt", "yahoo", "sec")
                 for i in range(35)]
        selected = news.select_evidence(
            items, self.event, "NVDA", "NVIDIA Corporation",
            self.event - timedelta(days=180), self.event + timedelta(days=2))
        counts = {source: sum(a["source"] == source for a in selected)
                  for source in ("nyt", "yahoo", "sec")}
        self.assertLessEqual(len(selected), news.COMBINED_ARTICLE_CAP)
        self.assertEqual(counts, news.SOURCE_CAPS)

    def test_yahoo_requires_a_direct_company_mention(self):
        relevant = self.article("yahoo", 1, "Nvidia reports quarterly results")
        unrelated = self.article("yahoo", 2, "A retailer announces a dividend")
        unrelated["snippet"] = "No connection to the investigated company."
        selected = news.select_evidence(
            [relevant, unrelated], self.event, "NVDA", "NVIDIA Corporation",
            self.event - timedelta(days=10), self.event + timedelta(days=2))
        self.assertEqual([a["headline"] for a in selected], [relevant["headline"]])

    def test_yahoo_related_ticker_metadata_can_fill_minimum_timeline(self):
        items = []
        for index in range(12):
            item = self.article("yahoo", index, f"Semiconductor industry update {index}")
            item["snippet"] = "Industry reporting without a ticker in the visible text."
            item["related_tickers"] = ["NVDA"]
            items.append(item)
        selected = news.select_evidence(
            items, self.event, "NVDA", "NVIDIA Corporation",
            self.event - timedelta(days=10), self.event + timedelta(days=2))
        self.assertGreaterEqual(len(selected), news.MIN_TIMELINE_POINTS)

    def test_near_duplicate_headlines_collapse(self):
        first = self.article("nyt", 1, "Nvidia reports record quarterly profit")
        second = self.article("yahoo", 2, "Nvidia reports record quarterly profits")
        selected = news.select_evidence(
            [first, second], self.event, "NVDA", "NVIDIA Corporation",
            self.event - timedelta(days=10), self.event + timedelta(days=2))
        self.assertEqual(len(selected), 1)


if __name__ == "__main__":
    unittest.main()
