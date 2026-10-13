"""Non-network tests of all three lanes, cross-repo auth, receipts and gating."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import unittest
from urllib.error import HTTPError

from management.core import (
    load_manifest, make_plan, manager, plan_matrix, qa, sha, signed,
    verify_receipt,
)
from management.github import Client, process_lane

CONFIG = Path(__file__).resolve().parents[1] / 'config/projects.json'
COMMIT = 'a' * 40
TIME = datetime(2026, 10, 13, 0, 0, tzinfo=timezone.utc)


class Reply:
    status = 200

    def __init__(self, result, status=200):
        self.result = result
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return json.dumps(self.result).encode()[:limit] if self.result is not None else b''


def fake_transport(req, timeout):
    assert timeout == 12
    assert req.full_url.startswith('https://api.github.com/repos/alfaauliau-katarinaAI/')
    if req.method == 'GET' and req.full_url.endswith('/runs?per_page=1'):
        return Reply({'workflow_runs': [{
            'id': 123456, 'status': 'completed', 'conclusion': 'success',
        }]})
    if req.method == 'GET' and '/actions/workflows/' in req.full_url:
        name = req.full_url.split('/')[-1]
        return Reply({'state': 'active', 'path': '.github/workflows/' + name})
    if req.method == 'POST' and req.full_url.endswith('/dispatches'):
        assert json.loads(req.data)['ref'] == 'main'
        return Reply(None, 204)
    raise AssertionError('Unexpected network URL ' + req.full_url)


class ManagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_manifest(CONFIG)

    def plan(self, scope='all', mode='audit'):
        return make_plan(self.cfg, scope, mode, COMMIT, '321', now=TIME)

    def test_manifest_exact_repo_allowlist(self):
        self.assertEqual([x['id'] for x in self.cfg['projects']],
                         ['ai', 'freelance', 'web'])
        self.assertEqual(self.cfg['max_parallel'], 3)

    def test_dynamic_matrix_three_simultaneous_lanes(self):
        plan = self.plan()
        self.assertEqual(plan_matrix(plan), {'include': [
            {'project': 'ai'}, {'project': 'freelance'}, {'project': 'web'}]})
        self.assertEqual(plan['max_parallel'], 3)
        self.assertEqual(plan['retry_limit'], 0)
        self.assertFalse(plan['applications_allowed'])
        self.assertFalse(plan['web_deployment_allowed'])
        self.assertFalse(plan['git_writes_allowed'])
        self.assertFalse(plan['trading_allowed'])

    def test_project_scopes_do_not_run_other_lanes(self):
        for project in ('ai', 'freelance', 'web'):
            plan = self.plan(scope=project)
            self.assertEqual(plan['project_lanes'], [project])
            self.assertEqual(len(plan_matrix(plan)['include']), 1)

    def test_invalid_manifest_fails_closed(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            cfg = json.loads(CONFIG.read_text())
            cfg['projects'][1]['workflow'] = 'deploy-autonomous.yml'
            path = Path(directory) / 'projects.json'
            path.write_text(json.dumps(cfg))
            with self.assertRaises(ValueError):
                load_manifest(path)

    def test_missing_private_token_blocks_without_api_call(self):
        def forbidden(*a, **kw):
            raise AssertionError('Private repo was contacted without token')
        result = process_lane(self.plan(), 'freelance',
                              github_token='job-token', transport=forbidden)
        self.assertEqual(result['status'], 'BLOCKED_AUTH')
        self.assertEqual(result['message'], 'PRIVATE_READ_TOKEN_NOT_CONFIGURED')

    def test_all_three_github_ci_status_reads_work(self):
        p = self.plan()
        reports = {}
        for lane in p['project_lanes']:
            result = process_lane(p, lane, github_token='gh-example',
                                  private_read_token='read-example',
                                  transport=fake_transport)
            self.assertEqual(result['status'], 'HEALTH_OK')
            self.assertEqual(result['observed_run_id'], 123456)
            reports[lane] = result
        check = qa(p, reports)
        result = manager(p, check)
        self.assertEqual(result['overall_status'], 'ALL_TRACKS_AUDITED')
        self.assertEqual(set(result['tracks']), {'ai', 'freelance', 'web'})
        self.assertTrue(result['no_auto_application'])
        self.assertTrue(result['no_auto_deployment'])
        self.assertTrue(result['no_live_trading'])

    def test_dispatch_requires_distinct_actions_write_token(self):
        def forbidden(*a, **kw):
            raise AssertionError('Dispatch without token must be offline')
        result = process_lane(self.plan(mode='dispatch'), 'ai',
                              github_token='repo-only-token',
                              transport=forbidden)
        self.assertEqual(result['status'], 'BLOCKED_AUTH')
        self.assertIsNone(result['dispatched_run_url'])

    def test_explicit_dispatch_is_accepted_not_misreported_finished(self):
        p = self.plan(mode='dispatch')
        result = process_lane(p, 'ai', dispatch_token='write-example',
                              transport=fake_transport)
        self.assertEqual(result['status'], 'DISPATCH_ACCEPTED')
        self.assertFalse(result['proven_completed_task'])
        self.assertIsNone(result['observed_conclusion'])
        summaries = {}
        for lane in p['project_lanes']:
            summaries[lane] = process_lane(
                p, lane, dispatch_token='write-example',
                transport=fake_transport)
        overall = manager(p, qa(p, summaries))
        self.assertEqual(overall['overall_status'], 'AWAITING_REMOTE_RESULTS')

    def test_tampered_receipt_rejected_by_qa(self):
        p = self.plan()
        reports = {lane: process_lane(p, lane, github_token='test',
                   private_read_token='read', transport=fake_transport)
                   for lane in p['project_lanes']}
        reports['web']['status'] = 'HEALTH_OK_FAKE'
        with self.assertRaises(ValueError):
            qa(p, reports)

    def test_cross_project_receipts_rejected_by_qa(self):
        p = self.plan()
        reports = {lane: process_lane(p, lane, github_token='test',
                   private_read_token='read', transport=fake_transport)
                   for lane in p['project_lanes']}
        reports['ai'] = reports['web']
        with self.assertRaises(ValueError):
            qa(p, reports)

    def test_partial_private_auth_reports_blocked_not_success(self):
        p = self.plan()
        reports = {lane: process_lane(p, lane, github_token='gh-example',
                   transport=fake_transport) for lane in p['project_lanes']}
        summary = manager(p, qa(p, reports))
        self.assertEqual(summary['overall_status'], 'PARTIALLY_BLOCKED')
        self.assertEqual(summary['blocked_projects'], ['freelance'])
        self.assertEqual(summary['tracks']['ai']['status'], 'HEALTH_OK')
        self.assertEqual(summary['tracks']['web']['status'], 'HEALTH_OK')

    def test_http_auth_error_does_not_leak_provider_body(self):
        def forbidden(req, timeout):
            raise HTTPError(req.full_url, 403, 'PRIVATE_ANSWER', {}, None)
        report = process_lane(self.plan(), 'freelance',
                              private_read_token='do-not-display-this-token',
                              transport=forbidden)
        self.assertEqual(report['status'], 'BLOCKED_AUTH')
        self.assertNotIn('do-not-display-this-token', json.dumps(report))
        self.assertNotIn('PRIVATE_ANSWER', json.dumps(report))

    def test_untrusted_endpoint_cannot_be_used(self):
        with self.assertRaises(ValueError):
            Client('x', fake_transport).call('https://untrusted.example.com')
        with self.assertRaises(ValueError):
            Client('x', fake_transport).call('/repos/not-the-owner/other')

    def test_qa_handoff_refuses_modified_plan(self):
        plan = self.plan()
        reports = {lane: process_lane(plan, lane, github_token='ok',
                   private_read_token='ok', transport=fake_transport)
                   for lane in plan['project_lanes']}
        verified = qa(plan, reports)
        verified['plan_receipt_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            manager(plan, verified)


if __name__ == '__main__':
    unittest.main()
