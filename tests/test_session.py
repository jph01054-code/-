from datetime import timedelta
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
from smartstore.rules import now_kst
from smartstore.session import Session, Stopped, Expired
from smartstore.browser import NeedsReview
from test_core import settings


class SessionTests(unittest.TestCase):
    def session(self,**kw):
        return Session(settings(**kw),Path('.'),lambda *_:None)

    def test_arm_only_once_after_browser_ready(self):
        s=self.session()
        self.assertFalse(s.arm())
        s.ready_event.set()
        self.assertTrue(s.arm())
        self.assertFalse(s.arm())

    def test_stop_overrides_pause(self):
        s=self.session()
        s.pause_event.set()
        s.stop_event.set()
        with self.assertRaises(Stopped):
            s.check()

    def test_expiration(self):
        s=self.session()
        s.deadline_at=now_kst()-timedelta(seconds=1)
        with self.assertRaises(Expired):
            s.check()

    def test_access_denied_not_retried(self):
        page=Mock()
        page.reload.return_value.status=429
        s=self.session()
        s.arm_event.set()
        with self.assertRaises(NeedsReview):
            s.monitor(page,'https://practice.invalid/products/1')
        self.assertEqual(page.reload.call_count,1)

    def test_waits_before_scheduled_time(self):
        s=self.session(mode='live',opening='2099-10-20 10:00:00')
        s.arm_event.set()
        page=Mock()
        s.idle=Mock(side_effect=Stopped())
        with self.assertRaises(Stopped):
            s.monitor(page,settings().url)
        page.reload.assert_not_called()

    def test_retry_backoff_stops_after_five_errors(self):
        s=self.session(interval=1)
        s.arm_event.set()
        s.idle=Mock()
        page=Mock()
        page.reload.return_value.status=503
        with self.assertRaises(NeedsReview):
            s.monitor(page,'https://practice.invalid/products/1')
        self.assertEqual(page.reload.call_count,5)
        self.assertEqual([c.args[1] for c in s.idle.call_args_list],[2,4,5,5])
