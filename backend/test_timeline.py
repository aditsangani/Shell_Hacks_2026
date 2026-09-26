"""Timeline regressions: failed providers, cache upgrades, and polling. No network."""
import json
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import timeline
import app
from test_conclusion import investigation_fixture


def fixture():
    return {**investigation_fixture(), 'company': 'Meta Platforms', 'market': 'SPY',
            'sector_etf': 'XLC', 'sector_known': False, 'mode': 'latest',
            'event_date': '2026-09-25', 'prior_session_date': '2026-09-24',
            'event_label': 'Sep 25, 2026', 'event_short': 'Sep 25', 'freshness': {},
            'move': {**investigation_fixture()['move'], 'z_score': 4.0},
            'divergence': {**investigation_fixture()['divergence'], 'beta_1y': 1.3}}


def article():
    return {'ref': 'A1', 'headline': 'Meta releases quarterly results',
            'pub_date': '2026-09-25T12:00:00+00:00', 'url': 'https://example.com/meta',
            'snippet': 'Meta reporting', 'source': 'nyt', 'publisher': 'The New York Times'}


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for name, value in [('CACHE_DIR', Path(self.temp.name)), ('_jobs', {}),
                            ('GEMINI_API_KEY', 'test-key')]:
            p = patch.object(timeline, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.inv = fixture()
        self.pool = [article()]
        self.write_pool()

    def write_pool(self):
        timeline._write_json(timeline._pool_path('META', '2026-09-25', 'latest'),
                             {'schema': timeline.EVIDENCE_POOL_VERSION, 'articles': self.pool})

    def build(self, **kwargs):
        return timeline.build('META', 'latest', self.inv, **kwargs)

    def settled(self, **kwargs):
        timeline._set_job('META', 'latest', state='done', finished=time.time(), **kwargs)

    def write_triage(self, events):
        timeline._write_json(timeline._triage_path('META', '2026-09-25', 'latest'),
                             {'timing_schema': timeline.TIMING_SCHEMA_VERSION, 'events': events,
                              'pool_fingerprint': timeline._pool_fingerprint(self.pool)})

    @patch.object(timeline, 'missing_chunks', return_value=0)
    def test_failed_triage_keeps_browsable_sources_without_causal_claims(self, _):
        self.settled(note='Gemini unavailable', quota_exhausted=True)
        with patch.object(timeline, 'start_warm') as warm:
            result = self.build()
        warm.assert_not_called()
        self.assertFalse(result['warming'])
        self.assertEqual(result['events'], [])
        self.assertEqual(len(result['candidates']), 1)
        self.assertFalse(result['candidates'][0]['can_explain_move'])
        self.assertEqual(result['conclusion']['evidence_status'], 'untriaged')

    @patch.object(timeline, 'missing_chunks', return_value=3)
    def test_missing_chunks_do_not_bypass_failure_cooldown(self, _):
        self.settled(note='NYT rate limit')
        with patch.object(timeline, 'start_warm') as warm:
            self.assertFalse(self.build()['warming'])
        warm.assert_not_called()

    @patch.object(timeline, 'missing_chunks', return_value=3)
    def test_cold_worker_error_does_not_restart_on_every_poll(self, _):
        timeline._pool_path('META', '2026-09-25', 'latest').unlink()
        timeline._set_job('META', 'latest', state='error', finished=time.time(), note='failed')
        with patch.object(timeline, 'start_warm') as warm:
            self.assertFalse(self.build()['warming'])
        warm.assert_not_called()

    @patch.object(timeline, 'missing_chunks', return_value=0)
    def test_empty_selection_still_exposes_sampled_coverage(self, _):
        self.write_triage([])
        result = self.build()
        self.assertEqual(result['events'], [])
        self.assertEqual(len(result['candidates']), 1)
        self.assertNotIn('triage_note', result)

    @patch.object(timeline, 'missing_chunks', return_value=0)
    def test_changed_pool_cannot_reuse_old_positional_citations(self, _):
        self.write_triage([{'ref': 'A1', 'scope': 'stock'}])
        self.pool[0]['url'] = 'https://example.com/different-article'
        self.write_pool()
        self.settled()
        result = self.build()
        self.assertEqual(result['events'], [])
        self.assertIn('triage_note', result)

    @patch.object(timeline, 'missing_chunks', return_value=0)
    def test_current_selected_event_keeps_verified_citation_and_timing(self, _):
        self.write_triage([{'ref': 'A1', 'scope': 'stock'}, {'ref': 'invented'}])
        result = self.build()
        self.assertEqual(len(result['events']), 1)
        self.assertEqual(result['events'][0]['url'], self.pool[0]['url'])
        self.assertTrue(result['events'][0]['can_explain_move'])

    @patch.object(timeline, 'missing_chunks', return_value=0)
    def test_refresh_does_not_start_duplicate_worker(self, _):
        timeline._set_job('META', 'latest', state='running')
        with patch.object(timeline, 'start_warm') as warm:
            self.assertTrue(self.build(refresh=True)['warming'])
        warm.assert_not_called()

    @patch.object(timeline, 'missing_chunks', return_value=0)
    def test_new_session_keeps_polling_until_old_worker_finishes(self, _):
        timeline._set_job('META', 'latest', state='running', event_date='2026-09-24')
        with patch.object(timeline, 'start_warm') as warm:
            self.assertTrue(self.build()['warming'])
        warm.assert_not_called()

    @patch.object(timeline, 'missing_chunks', return_value=0)
    def test_no_key_still_allows_source_browsing(self, _):
        with patch.object(timeline, 'GEMINI_API_KEY', ''), \
             patch.object(timeline, 'start_warm') as warm:
            result = self.build()
        warm.assert_not_called()
        self.assertFalse(result['warming'])
        self.assertEqual(len(result['candidates']), 1)

    @patch.object(timeline, 'missing_chunks', return_value=0)
    def test_failure_cooldown_survives_restart(self, _):
        timeline._write_json(timeline.CACHE_DIR / 'warm_META_2026-09-25_latest.json',
                             {'state': 'done', 'note': 'unavailable', 'finished': time.time()})
        with patch.object(timeline, 'start_warm') as warm:
            self.assertFalse(self.build()['warming'])
        warm.assert_not_called()

    def test_cached_short_page_exhausts_cell(self):
        with patch.object(timeline.news, 'NYT_API_KEY', 'test'), \
             patch.object(timeline.market, 'plan_cells', return_value=[('2026', date(2026, 1, 1), date(2026, 9, 25))]), \
             patch.object(timeline.news, '_reusable_term_cache', return_value={('2026', 0): [article()]}):
            self.assertEqual(timeline.missing_chunks(date(2026, 9, 25), 'META', 'latest', 'Meta'), 0)

    def test_bad_timestamp_is_isolated(self):
        bad = {**article(), 'pub_date': 'invalid'}
        self.assertEqual(len(timeline._timed_articles([bad, article()], self.inv)), 1)

    def test_model_fallback_and_cache_fingerprint(self):
        with patch.object(timeline, 'GEMINI_MODEL', 'primary'), \
             patch.object(timeline, 'GEMINI_FALLBACK_MODEL', 'fallback'), \
             patch.object(timeline.genai, 'Client') as client:
            generate = client.return_value.models.generate_content
            generate.side_effect = [RuntimeError('503 unavailable'), SimpleNamespace(text=json.dumps({'events': []}))]
            result = timeline._triage(self.inv, self.pool, timeline.scope_verdict(self.inv['divergence']), 180)
            self.assertEqual(result['model'], 'fallback')
            self.assertEqual(result['pool_fingerprint'], timeline._pool_fingerprint(self.pool))
            self.assertEqual(generate.call_count, 2)

    @patch.object(timeline, 'missing_chunks', return_value=0)
    def test_api_serves_candidates_during_ai_failure(self, _):
        self.settled(note='Gemini unavailable')
        with patch.object(app, '_investigation', return_value=self.inv):
            response = app.app.test_client().get('/api/timeline?symbol=META&mode=latest')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json['candidates']), 1)

    def test_warm_endpoint_returns_json_error(self):
        with patch.object(app, '_investigation', side_effect=RuntimeError('price source unavailable')):
            response = app.app.test_client().post('/api/timeline/warm?symbol=META')
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json['error'], 'price source unavailable')


if __name__ == '__main__':
    unittest.main()
