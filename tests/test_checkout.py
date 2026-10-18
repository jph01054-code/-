import unittest
from pathlib import Path
from smartstore.checkout import CheckoutPage
from smartstore.browser import NeedsReview, resolve_option
from smartstore.demo import order_html, DEMO_URL, DemoStore
from smartstore.rules import OneShot
from smartstore.session import Session
from test_browser import BrowserFixture
from test_core import settings


class CheckoutTests(BrowserFixture):
    def test_points_card_delivery_and_single_payment(self):
        values=settings(card='신한카드',points_mode='amount',points_amount=5000,auto_pay=True)
        self.fixture(order_html(1,values))
        checkout=CheckoutPage(self.page,demo=True)
        latch=OneShot()
        amount=checkout.submit(values,values.option,latch,lambda:None)
        self.assertEqual(amount,38000)
        self.assertTrue(self.page.get_by_role('radio',name='신한카드',exact=True).is_checked())
        self.assertEqual(self.page.evaluate('window.payClicks'),1)
        self.assertTrue(checkout.authenticate('123456',lambda:None))
        self.assertEqual(self.page.evaluate('window.authClicks'),1)
        with self.assertRaises(RuntimeError):
            checkout.submit(values,values.option,latch,lambda:None)
        self.assertEqual(self.page.evaluate('window.payClicks'),1)


    def test_full_points(self):
        values=settings(points_mode='all',auto_pay=True)
        self.fixture(order_html(1,values))
        amount=CheckoutPage(self.page,demo=True).submit(values,values.option,OneShot(),lambda:None)
        self.assertEqual(amount,33000)


    def test_limit_stops_payment(self):
        values=settings(limit=40000,auto_pay=True)
        self.fixture(order_html(1,values))
        with self.assertRaises(NeedsReview):
            CheckoutPage(self.page,demo=True).submit(values,values.option,OneShot(),lambda:None)
        self.assertIsNone(self.page.evaluate('window.payClicks'))


    def test_wrong_quantity_stops_payment(self):
        values=settings(auto_pay=True)
        self.fixture(order_html(2,values))
        with self.assertRaises(NeedsReview):
            CheckoutPage(self.page,demo=True).submit(values,values.option,OneShot(),lambda:None)
        self.assertIsNone(self.page.evaluate('window.payClicks'))


    def test_other_host_never_receives_password(self):
        self.fixture(order_html(1))
        self.assertRaises(NeedsReview,CheckoutPage(self.page).authenticate,'123456',lambda:None)
        self.assertEqual(self.page.locator('#password').input_value(),'')


    def test_readonly_keypad_requires_user(self):
        self.fixture(order_html(1))
        self.page.locator('#auth').evaluate('(e)=>e.hidden=false')
        self.page.locator('#password').evaluate('(e)=>e.readOnly=true')
        self.assertFalse(CheckoutPage(self.page,demo=True).authenticate('123456',lambda:None))
        self.assertEqual(self.page.locator('#password').input_value(),'')


    def test_entire_demo_through_payment_and_auth(self):
        values=settings(option='블랙',points_mode='all',card='국민카드',auto_pay=True,interval=1)
        store=DemoStore(values)
        self.context.route('**/*',store.handle)
        self.page.goto(DEMO_URL)
        events=[]
        session=Session(values,Path('.'),lambda kind,value:events.append((kind,value)),password='123456')
        session.arm_event.set()
        session.hold=lambda *_:None
        session.monitor(self.page,DEMO_URL)
        self.assertEqual(self.page.evaluate('window.payClicks'),1)
        self.assertEqual(self.page.evaluate('window.authClicks'),1)
        self.assertEqual(session.password,'')
        self.assertTrue(any(kind=='selected' and value=='블랙' for kind,value in events))
        self.assertFalse(any('123456' in str(value) for _,value in events))


class SearchTests(unittest.TestCase):
    def test_substring_match(self):
        self.assertEqual(resolve_option('블랙',['화이트','2. 블랙 L']),'2. 블랙 L')

    def test_ambiguous_requires_selection(self):
        with self.assertRaises(NeedsReview):
            resolve_option('블랙',['블랙 S','블랙 L'])
        self.assertEqual(resolve_option('블랙',['블랙 S','블랙 L'],'블랙 L'),'블랙 L')
