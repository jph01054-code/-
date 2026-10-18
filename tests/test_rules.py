import unittest
from datetime import datetime
from smartstore.rules import validate, watch_time, same_product, option_pattern, OneShot


class RulesTests(unittest.TestCase):
    def setUp(self):
        self.values = dict(url='https://brand.naver.com/skinfood/products/13763129062',
            option='감자 수딩 패드 60매(+마스크팩2매)',quantity='1',limit='50000',
            interval='2',opening='2026-10-19 10:00:00')

    def test_valid(self):
        self.assertEqual(validate(self.values)['quantity'],1)

    def test_schedule(self):
        self.assertEqual(watch_time(self.values['opening']),datetime(2026,10,19,9,59))

    def test_reject_invalid(self):
        for changes in [dict(url='https://brand.naver.com.evil.test/a/products/1'),
            dict(quantity='0'),dict(limit='0'),dict(interval='.1'),dict(interval='nan'),dict(option='')]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                validate(dict(self.values,**changes))

    def test_same_product(self):
        self.assertTrue(same_product(self.values['url']+'?x=1',self.values['url']))
        self.assertFalse(same_product('https://brand.naver.com/skinfood/products/1',self.values['url']))

    def test_option_exact(self):
        pattern=option_pattern(self.values['option'])
        self.assertTrue(pattern.fullmatch('감자 수딩 패드 60매 (+마스크팩 2매)'))
        self.assertFalse(pattern.fullmatch('감자 수딩 패드 60매 (+마스크팩 3매)'))

    def test_no_duplicate(self):
        latch=OneShot()
        latch.claim()
        with self.assertRaises(RuntimeError):
            latch.claim()
