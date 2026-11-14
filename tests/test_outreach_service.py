from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from sqlalchemy import create_engine

from backend.facebook.parsers.post_date import VIETNAM_TZ
from backend.services.outreach_service import OutreachService, normalize_target, render_content
from backend.services.outreach_scheduler import OutreachScheduler
from backend.workers.browser_worker import BrowserWorker


class OutreachServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_engine(f'sqlite:///{Path(self.directory.name)/"outreach.db"}')
        self.now = datetime(2026, 11, 13, 8, tzinfo=VIETNAM_TZ)
        self.service = OutreachService(self.engine, clock=lambda: self.now)

    def tearDown(self):
        self.engine.dispose()
        self.directory.cleanup()

    def target(self, number=1, kind='thread'):
        urls = {'thread': f'https://facebook.com/messages/t/{number}',
                'person': f'https://facebook.com/{number}', 'group': f'https://facebook.com/groups/{number}',
                'post': f'https://facebook.com/example/posts/{number}'}
        return dict(kind=kind, url=urls[kind], name=f'Khách {number}', industry='Gia dụng', region='Hà Nội')

    def schedule(self, **kwargs):
        options = dict(profile='nick-a', campaign='Chăm sóc', action='message', targets=[self.target()],
                       content='Chào {ten}, em tư vấn {nganh} ở {khu_vuc}', run_at=self.now,
                       gap_seconds=0, daily_limit=20)
        options.update(kwargs)
        return self.service.schedule(**options)['ids']

    def test_target_validation_rejects_navigation_external_and_comment_links(self):
        self.assertEqual(normalize_target('person', 'https://m.facebook.com/profile.php?id=123&ref=share'),
                         'https://www.facebook.com/profile.php?id=123')
        self.assertEqual(normalize_target('thread', 'https://messenger.com/e2ee/t/123?ref=foo'),
                         'https://www.facebook.com/messages/e2ee/t/123/')
        for kind, url in [('person', 'https://facebook.com/messages'), ('person', 'https://evil.com/123'),
                          ('thread', 'https://facebook.com/messages/t/name'),
                          ('thread', 'https://user@facebook.com/messages/t/12'),
                          ('post', 'https://facebook.com/groups/1/posts/2/?comment_id=3')]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalize_target(kind, url)
        for text in ['{ten.__class__}', '{ten!r}', '{nganh:>100}', '{unknown}', '{']:
            with self.assertRaises(ValueError):
                render_content(text, self.target())

    def test_audiences_are_owned_by_profile_and_tags_survive_rediscovery(self):
        self.service.save_targets('nick-a', [self.target(1, 'group')])
        row = self.service.targets('nick-a')[0]
        self.service.tag_targets('nick-a', [row['id']], 'Nội thất', 'Đà Nẵng')
        self.service.save_targets('nick-a', [dict(self.target(1, 'group'), industry='', region='')])
        self.assertEqual(len(self.service.targets('nick-a', industry='noi that', region='da nang')), 1)
        self.assertEqual(self.service.targets('nick-b'), [])
        with self.assertRaises(ValueError):
            self.service.save_targets('nick-a', [self.target(2), dict(self.target(3), url='https://evil.com/t/3')])
        self.assertEqual(len(self.service.targets('nick-a')), 1)

    def test_scheduler_switch_survives_reopening(self):
        self.assertTrue(self.service.scheduler_enabled())
        self.service.set_scheduler_enabled(False)
        reopened = OutreachService(self.engine)
        self.assertFalse(reopened.scheduler_enabled())
        reopened.set_scheduler_enabled(True)
        self.assertTrue(self.service.scheduler_enabled())

    def test_preview_has_no_side_effects_and_queue_deduplicates_reviewed_content(self):
        rows = self.service.prepare_schedule(profile='nick-a', campaign='Test', action='message',
            targets=[self.target()], content='Chào {ten} ở {khu_vuc}')
        self.assertEqual(rows[0]['content'], 'Chào Khách 1 ở Hà Nội')
        self.assertEqual(self.service.list_jobs(), [])
        self.assertEqual(len(self.schedule()), 1)
        self.assertEqual(self.schedule(), [])
        self.assertEqual(len(OutreachService(self.engine).list_jobs()), 1)
        with self.assertRaises(ValueError):
            self.schedule(targets=[self.target(2), self.target(3, 'person')])
        self.assertEqual(len(self.service.list_jobs()), 1)
        with self.assertRaises(ValueError):
            self.schedule(repeat_days=1)
        with self.assertRaises(ValueError):
            self.schedule(action='group_post', targets=[self.target(1, 'group')], media=['missing.jpg'])

    def test_atomic_claim_reserves_only_one_action_per_profile(self):
        ids = self.schedule(targets=[self.target(1), self.target(2)])
        with ThreadPoolExecutor(max_workers=2) as pool:
            claimed = list(pool.map(self.service.claim, ids))
        self.assertEqual(sum(row is not None for row in claimed), 1)
        self.assertEqual(len(self.service.history()), 1)

    def test_daily_budget_cooldown_and_pause_are_enforced_across_campaigns(self):
        first, second = self.schedule(targets=[self.target(1), self.target(2)], gap_seconds=60, daily_limit=1)
        self.service.control([first], 'pause')
        self.assertIsNone(self.service.claim(first))
        self.service.control([first], 'resume')
        running = self.service.claim(first)
        self.assertIsNotNone(running)
        self.service.finish(first, running['token'], 'sent', 'Đã gửi')
        self.assertIsNone(self.service.claim(second))
        self.now += timedelta(days=1)
        self.assertIsNotNone(self.service.claim(second))
        self.assertEqual(len(self.service.history(self.now.date(), profile='nick-a')), 1)

    def test_cooldown_applies_to_different_actions_of_same_profile(self):
        first = self.schedule(gap_seconds=60)[0]
        second = self.schedule(action='add_friend', targets=[self.target(2, 'person')], content='', gap_seconds=60)[0]
        job = self.service.claim(first)
        self.service.finish(first, job['token'], 'sent', 'Sent')
        self.assertIsNone(self.service.claim(second))
        self.now += timedelta(seconds=61)
        self.assertIsNotNone(self.service.claim(second))

    def test_recurring_care_skips_missed_runs_and_cancel_stops_recurrence(self):
        job_id = self.schedule(action='engage', targets=[self.target(1, 'person')], content='', repeat_days=2)[0]
        self.now += timedelta(days=11)
        job = self.service.claim(job_id)
        self.service.finish(job_id, job['token'], 'done', 'Liked')
        scheduled = self.service.list_jobs()[0]
        self.assertEqual(scheduled['status'], 'queued')
        self.assertGreater(datetime.fromisoformat(scheduled['next_at']), self.now)
        self.now += timedelta(days=2)
        job = self.service.claim(job_id)
        self.service.control([job_id], 'cancel')
        self.assertTrue(self.service.is_cancelled(job_id, job['token']))
        self.service.finish(job_id, job['token'], 'done', 'Already finished before stop')
        self.assertEqual(self.service.list_jobs()[0]['status'], 'done')

    def test_interrupted_actions_need_review_and_old_tokens_cannot_commit(self):
        job_id = self.schedule()[0]
        job = self.service.claim(job_id)
        self.assertFalse(self.service.finish(job_id, 'wrong-token', 'sent', 'Wrong'))
        self.now += timedelta(minutes=11)
        self.assertEqual(self.service.recover_stale(), 1)
        self.assertEqual(self.service.list_jobs()[0]['status'], 'review')
        self.assertEqual(self.service.history()[0]['status'], 'review')
        self.assertIsNone(self.service.claim(job_id))
        self.assertFalse(self.service.finish(job_id, job['token'], 'sent', 'Late response'))
        self.assertEqual(self.schedule(), [])
        self.service.control([job_id], 'cancel')
        self.assertEqual(len(self.schedule()), 1)

    def test_scheduler_waits_for_online_idle_profile_and_dispatches_on_owner_worker(self):
        self.schedule(targets=[self.target(1), self.target(2)])
        pool = Mock()
        pool.get_worker.return_value = Mock(operation_active=False)
        pool.get_session.return_value = SimpleNamespace(running=False, logged_in=False)
        scheduler = OutreachScheduler(self.service, pool=pool, start=False)
        scheduler.tick()
        pool.get_worker.return_value.outreach_requested.emit.assert_not_called()
        pool.get_session.return_value = SimpleNamespace(running=True, logged_in=True)
        scheduler.enabled = False
        scheduler.tick()
        pool.get_worker.return_value.outreach_requested.emit.assert_not_called()
        scheduler.enabled = True
        scheduler.tick()
        self.assertEqual(pool.get_worker.return_value.outreach_requested.emit.call_count, 1)
        request = pool.get_worker.return_value.outreach_requested.emit.call_args.args[0]
        self.assertEqual(request['job']['profile'], 'nick-a')
        self.assertIs(request['service'], self.service)

    def test_worker_uses_persisted_target_and_marks_uncertain_mutations_for_review(self):
        job_id = self.schedule()[0]
        job = self.service.claim(job_id)
        worker = BrowserWorker()
        worker.profile_name = 'nick-a'
        with patch('backend.workers.browser_worker.browser_pool') as pool, \
             patch('backend.workers.browser_worker.OutreachBrowser') as browser, \
             patch('backend.workers.browser_worker.AppLogger'):
            pool.get_session.return_value = SimpleNamespace(running=True, logged_in=True)
            browser.return_value.mutated = True
            browser.return_value.perform.side_effect = RuntimeError('Disconnected after Enter')
            worker.run_outreach(dict(service=self.service, job=dict(job, target='https://evil.com')))
            self.assertEqual(browser.return_value.perform.call_args.args[0]['target'], self.service.list_jobs()[0]['target'])
            self.assertEqual(self.service.list_jobs()[0]['status'], 'review')
            self.assertFalse(worker.operation_active)

    def test_group_campaign_cannot_publish_to_groups_outside_the_profile_membership(self):
        job_id = self.schedule(action='group_post', targets=[self.target(1, 'group')], content='Bài đã duyệt')[0]
        job = self.service.claim(job_id)
        worker = BrowserWorker()
        worker.profile_name = 'nick-a'
        with patch('backend.workers.browser_worker.browser_pool') as pool, \
             patch('backend.workers.browser_worker.GroupService') as groups, \
             patch('backend.workers.browser_worker.OutreachBrowser') as browser, \
             patch('backend.workers.browser_worker.AppLogger'):
            pool.get_session.return_value = SimpleNamespace(running=True, logged_in=True)
            groups.return_value.get_for_profile.return_value = []
            worker.run_outreach(dict(service=self.service, job=job))
            browser.assert_not_called()
            self.assertEqual(self.service.list_jobs()[0]['status'], 'failed')

    def test_cancelled_job_does_not_open_a_browser_and_busy_worker_remains_busy(self):
        job_id = self.schedule()[0]
        job = self.service.claim(job_id)
        self.service.control([job_id], 'cancel')
        worker = BrowserWorker()
        worker.profile_name = 'nick-a'
        with patch('backend.workers.browser_worker.browser_pool') as pool:
            worker.run_outreach(dict(service=self.service, job=job))
            pool.get.assert_not_called()
        self.assertEqual(self.service.list_jobs()[0]['status'], 'cancelled')
        job_id = self.schedule(targets=[self.target(2)])[0]
        job = self.service.claim(job_id)
        worker.operation_active = True
        with patch('backend.workers.browser_worker.AppLogger'):
            worker.run_outreach(dict(service=self.service, job=job))
        self.assertTrue(worker.operation_active)


if __name__ == '__main__':
    unittest.main()
