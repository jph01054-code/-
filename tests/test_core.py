from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from smartstore.rules import Settings, KST, defaults, option_pattern, same_product, OneShot
from smartstore.storage import load, save


def settings(**changes):
    return replace(Settings(url='https://brand.naver.com/skinfood/products/13763129062',
        option='감자 수딩 패드 60매(+마스크팩2매)', opening='2026-10-20 10:00:00'), **changes)


class SettingsTests(unittest.TestCase):
    def test_watch_time_in_korea(self):
        self.assertEqual(settings().start_at, datetime(2026,10,20,9,59,tzinfo=KST))

    def test_explicit_ticketing_start(self):
        self.assertEqual(settings(start_time='2026-10-20 09:58:30').start_at,
                         datetime(2026,10,20,9,58,30,tzinfo=KST))

    def test_watch_can_cross_day(self):
        self.assertEqual(settings(opening='2026-10-20 00:00:00').start_at,
                         datetime(2026,10,19,23,59,tzinfo=KST))

    def test_deadline_extends_from_late_arm(self):
        armed = datetime(2026,10,20,10,10,tzinfo=KST)
        self.assertEqual(settings().deadline(armed), armed+timedelta(minutes=20))

    def test_next_default_opening_is_future_korea_time(self):
        with patch('smartstore.rules.now_kst', return_value=datetime(2026,10,20,12,tzinfo=KST)):
            self.assertEqual(defaults().opening, '2026-10-21 10:00:00')

    def test_invalid_inputs(self):
        for change in [dict(url='https://brand.naver.com.evil.test/x/products/1'),
            dict(url='https://user:password@brand.naver.com/x/products/1'),
            dict(quantity=0),dict(limit=0),dict(interval=.1),dict(interval=float('nan')),
            dict(interval=float('inf')),dict(duration=0),dict(option=''),dict(mode='other'),
            dict(opening='2026-02-30 10:00:00'),dict(action='pay')]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                settings(**change).validate()

    def test_int_fields_cannot_truncate_floats(self):
        with self.assertRaises(ValueError):
            Settings.from_dict(dict(settings().to_dict(),quantity=1.5))

    def test_option_whitespace_only(self):
        p = option_pattern(settings().option)
        self.assertTrue(p.fullmatch('감자 수딩 패드 60매 (+마스크팩 2매)'))
        self.assertFalse(p.fullmatch('감자 수딩 패드 60매 (+마스크팩 3매)'))

    def test_product_identity(self):
        url = settings().url
        self.assertTrue(same_product(url+'?x=1',url))
        self.assertFalse(same_product(url.replace('13763129062','1'),url))

    def test_one_shot(self):
        latch=OneShot()
        latch.claim()
        with self.assertRaises(RuntimeError):
            latch.claim()


class StorageTests(unittest.TestCase):
    def test_password_is_not_a_saved_setting(self):
        values=settings().to_dict()
        values['password']='123456'
        actual=Settings.from_dict(values)
        self.assertNotIn('password',actual.to_dict())
    def test_roundtrip_and_live_mode_reset(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'settings.json'
            save(path,settings(mode='live'))
            actual,warning=load(path)
            self.assertIsNone(warning)
            self.assertEqual(actual.mode,'demo')
            self.assertEqual(actual.option,settings().option)

    def test_malformed_file_preserved(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'settings.json'
            path.write_text('{bad',encoding='utf-8')
            actual,warning=load(path)
            self.assertIsNotNone(warning)
            self.assertEqual(actual.mode,'demo')
            self.assertEqual(path.read_text(encoding='utf-8'),'{bad')
