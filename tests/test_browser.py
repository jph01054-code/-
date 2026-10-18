import os
import unittest
from playwright.sync_api import sync_playwright
from smartstore.browser import StorePage, NeedsReview
from smartstore.demo import DemoStore, DEMO_URL, product_html, order_html
from smartstore.rules import OneShot
from smartstore.session import Session
from pathlib import Path
from test_core import settings


class BrowserFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=sync_playwright().start()
        try:
            cls.browser=cls.p.chromium.launch(headless=True,
                executable_path=os.getenv('TEST_CHROMIUM_PATH'))
        except Exception:
            cls.p.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.p.stop()

    def setUp(self):
        self.context=self.browser.new_context()
        self.page=self.context.new_page()

    def tearDown(self):
        self.context.close()

    def fixture(self, content):
        self.context.route('**/*',lambda route:route.fulfill(body=content,
            content_type='text/html; charset=utf-8'))
        self.page.goto(DEMO_URL)
        return StorePage(self.page,DEMO_URL)


class BrowserTests(BrowserFixture):

    def test_sold_out_waits(self):
        adapter=self.fixture(product_html(settings(),False))
        self.assertFalse(adapter.prepare(settings(),OneShot(),lambda:None))

    def test_wrong_option_stops(self):
        adapter=self.fixture(product_html(settings(option='다른 옵션'),True))
        with self.assertRaises(NeedsReview):
            adapter.prepare(settings(),OneShot(),lambda:None)

    def test_quantity_unidentified_stops(self):
        adapter=self.fixture(product_html(settings(),True))
        self.page.locator('#qty').evaluate('(e)=>{e.removeAttribute("title");e.removeAttribute("aria-label")}')
        with self.assertRaises(NeedsReview):
            adapter.prepare(settings(),OneShot(),lambda:None)

    def test_duplicate_button_ambiguous(self):
        adapter=self.fixture(product_html(settings(),True))
        self.page.get_by_role('button',name='구매하기').evaluate('(e)=>document.body.appendChild(e.cloneNode(true))')
        self.assertIsNone(adapter.purchase_button())

    def test_emergency_stop_before_click(self):
        adapter=self.fixture(product_html(settings(),True))
        def stop():
            raise InterruptedError()
        with self.assertRaises(InterruptedError):
            adapter.prepare(settings(),OneShot(),stop)
        self.assertEqual(self.page.locator('#chosen').inner_text(),'')
        self.assertTrue(self.page.locator('#options').is_hidden())

    def test_order_result_and_one_shot(self):
        store=DemoStore(settings(quantity=2))
        store.visits=3
        self.context.route('**/*',store.handle)
        self.page.goto(DEMO_URL)
        latch=OneShot()
        adapter=StorePage(self.page,DEMO_URL)
        self.assertTrue(adapter.prepare(settings(quantity=2),latch,lambda:None))
        self.assertEqual(adapter.total(),83000)
        self.assertTrue(latch.used)
        self.assertIsNone(self.page.evaluate('window.payClicks'))
        self.page.goto(DEMO_URL)
        with self.assertRaises(RuntimeError):
            adapter.prepare(settings(quantity=2),latch,lambda:None)

    def test_ambiguous_total_unknown(self):
        adapter=self.fixture(order_html(1)+'<p>총 결제 금액 45,000원</p>')
        self.assertIsNone(adapter.total())

    def test_redirect_to_other_product_stops(self):
        adapter=self.fixture(product_html(settings(),True))
        self.page.goto('https://practice.invalid/products/2')
        with self.assertRaises(NeedsReview):
            adapter.purchase_button()

    def test_end_to_end_local_stock_and_limit_warning(self):
        values=settings(quantity=2,interval=1)
        store=DemoStore(values)
        self.context.route('**/*',store.handle)
        self.page.goto(DEMO_URL)
        events=[]
        session=Session(values,Path('.'),lambda kind,value:events.append((kind,value)))
        session.arm_event.set()
        # Replace only the final manual-browser wait, keeping the entire monitor.
        session.hold=lambda page,message:events.append(('hold',message))
        session.monitor(self.page,DEMO_URL)
        self.assertEqual(session.attempts,2)
        self.assertTrue(session.latch.used)
        self.assertTrue(any(kind=='log' and '한도 초과' in value for kind,value in events))
        self.assertTrue(self.page.url.startswith('https://practice.invalid/order'))

    def test_notify_never_selects_option_or_submits(self):
        values=settings(action='notify',interval=1)
        store=DemoStore(values)
        self.context.route('**/*',store.handle)
        self.page.goto(DEMO_URL)
        session=Session(values,Path('.'),lambda *_:None)
        session.arm_event.set()
        session.hold=lambda *_:None
        session.monitor(self.page,DEMO_URL)
        self.assertFalse(session.latch.used)
        self.assertEqual(self.page.url,DEMO_URL)
        self.assertEqual(self.page.locator('#chosen').inner_text(),'')
        self.assertTrue(self.page.locator('#qty').is_hidden())
