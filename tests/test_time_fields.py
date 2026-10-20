import unittest
from smartstore.time_fields import join_time,split_time
from smartstore.window_layout import halves
from smartstore.rules import Settings,OptionSpec
from test_core import settings


class TimeFieldTests(unittest.TestCase):
    def test_midnight_and_noon(self):
        for stamp,hour,ampm in [('2026-10-20 00:01:02','12','AM'),('2026-10-20 12:01:02','12','PM'),
                                ('2026-10-20 23:59:59','11','PM')]:
            with self.subTest(stamp=stamp):
                parts=split_time(stamp)
                self.assertEqual((parts['hour'],parts['ampm']),(hour,ampm))
                self.assertEqual(join_time(parts),stamp)

    def test_invalid_calendar_and_hour(self):
        parts=split_time('2026-10-20 10:00:00')
        for change in [dict(month='02',day='30'),dict(hour='00'),dict(minute='60'),dict(ampm='x')]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                join_time(dict(parts,**change))

    def test_half_screen_with_odd_width_and_offset(self):
        chrome,app=halves(1919,1040,-1920,30)
        self.assertEqual(chrome.width+app.width,1919)
        self.assertEqual(app.left,chrome.left+chrome.width)
        self.assertEqual((chrome.top,chrome.height),(30,1040))
        self.assertEqual((app.top,app.height),(30,1040))
        self.assertEqual(chrome.geometry(),'959x1040-1920+30')


class OptionSettingsTests(unittest.TestCase):
    def test_refresh_bounds(self):
        for value in [.1,5]:
            self.assertEqual(settings(interval=value).validate().interval,value)
        for value in [.099,5.001]:
            with self.assertRaises(ValueError):
                settings(interval=value).validate()

    def test_no_options_allows_empty_search(self):
        actual=settings(no_options=True,option='').validate()
        self.assertEqual(actual.groups,())

    def test_multiple_groups_roundtrip(self):
        actual=settings(option_groups=(OptionSpec('블랙','블랙'),OptionSpec('XL','XL')))
        self.assertEqual(Settings.from_dict(actual.to_dict()).groups,actual.groups)

    def test_malformed_groups_rejected(self):
        for groups in [None,'wrong',[1]]:
            with self.assertRaises(ValueError):
                Settings.from_dict(dict(settings().to_dict(),option_groups=groups))
