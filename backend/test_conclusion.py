"""Regression checks for the deterministic investigation conclusion."""

import unittest

import conclusion


def investigation_fixture() -> dict:
    return {
        "symbol": "META",
        "move": {
            "move_pct": 11.43,
            "percentile": 99.4,
            "history_days": 1259,
        },
        "divergence": {
            "ticker_pct": 11.43,
            "market_pct": 0.55,
            "beta_expected_pct": 0.72,
            "idiosyncratic_pct": 10.71,
        },
        "similar": [
            {"d1": 1.0, "d5": 2.0, "d20": 8.0},
            {"d1": -1.0, "d5": -2.0, "d20": -4.0},
            {"d1": 0.5, "d5": 1.0, "d20": 2.0},
        ],
    }


def verdict() -> dict:
    return {
        "verdict": "stock_specific",
        "share": 0.937,
        "label": "Stock-specific",
        "against_market": False,
    }


class DeterministicConclusionTests(unittest.TestCase):
    def test_possible_catalyst_is_qualified(self):
        evidence = {
            "verdict": verdict(),
            "pool_size": 3,
            "events": [{
                "can_explain_move": True,
                "publisher": "SEC EDGAR",
            }],
        }
        result = conclusion.build(investigation_fixture(), evidence)
        self.assertEqual(result["evidence_status"], "possible_catalyst")
        self.assertIn("does not establish", result["evidence"])
        self.assertEqual(result["method"], "computed")

    def test_later_only_coverage_is_not_called_a_catalyst(self):
        evidence = {
            "verdict": verdict(),
            "pool_size": 2,
            "events": [{"can_explain_move": False, "timing_role": "reaction"}],
        }
        result = conclusion.build(investigation_fixture(), evidence)
        self.assertEqual(result["evidence_status"], "no_published_catalyst")
        self.assertIn("reaction or context", result["evidence"])

    def test_untriaged_candidates_produce_no_evidence_claim(self):
        evidence = {
            "verdict": verdict(),
            "pool_size": 4,
            "events": [],
            "triage_note": "Gemini unavailable",
        }
        result = conclusion.build(investigation_fixture(), evidence)
        self.assertEqual(result["evidence_status"], "untriaged")
        self.assertIn("No claim", result["evidence"])

    def test_historical_summary_uses_median_and_sample_size(self):
        result = conclusion.build(investigation_fixture(), {"verdict": verdict(), "pool_size": 0})
        self.assertIn("2 finished positive", result["history"])
        self.assertIn("median return was +2.00%", result["history"])


if __name__ == "__main__":
    unittest.main()
