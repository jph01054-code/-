from smartstore.browser import NeedsReview,OptionChoiceRequired,StorePage
from smartstore.rules import OptionSpec,OneShot
from smartstore.demo import DemoStore,DEMO_URL,product_html
from smartstore.checkout import CheckoutPage
from test_browser import BrowserFixture
from test_core import settings


class ProductControlsTests(BrowserFixture):
    def test_two_option_groups_and_quantity(self):
        values=settings(quantity=2,option_groups=(OptionSpec('블랙'),OptionSpec('XL')))
        store=DemoStore(values)
        store.visits=3
        self.context.route('**/*',store.handle)
        self.page.goto(DEMO_URL)
        adapter=StorePage(self.page,DEMO_URL)
        snapshot=adapter.group_snapshot(lambda:None)
        self.assertEqual(len(snapshot),2)
        self.assertIn('블랙',snapshot[0]['labels'])
        self.assertIn('XL',snapshot[1]['labels'])
        self.assertTrue(adapter.prepare(values,OneShot(),lambda:None))
        self.assertEqual(adapter.selected_options,['블랙','XL'])
        CheckoutPage(self.page,demo=True).verify_item(values,adapter.selected_options)

    def test_no_options_purchase(self):
        values=settings(no_options=True,option='')
        store=DemoStore(values)
        store.visits=3
        self.context.route('**/*',store.handle)
        self.page.goto(DEMO_URL)
        adapter=StorePage(self.page,DEMO_URL)
        self.assertEqual(adapter.group_snapshot(lambda:None),[])
        self.assertTrue(adapter.prepare(values,OneShot(),lambda:None))
        self.assertEqual(adapter.selected_options,[])
        CheckoutPage(self.page,demo=True).verify_item(values,[])

    def test_no_options_refuses_real_groups(self):
        adapter=self.fixture(product_html(settings(),True))
        latch=OneShot()
        with self.assertRaises(NeedsReview):
            adapter.prepare(settings(no_options=True),latch,lambda:None)
        self.assertFalse(latch.used)

    def test_missing_second_query_requests_selection(self):
        values=settings(option_groups=(OptionSpec('블랙'),OptionSpec('')))
        adapter=self.fixture(product_html(values,True))
        latch=OneShot()
        with self.assertRaises(OptionChoiceRequired) as error:
            adapter.prepare(values,latch,lambda:None)
        self.assertEqual(error.exception.index,1)
        self.assertFalse(latch.used)

    def test_npay_link_recognized(self):
        adapter=self.fixture('<a href="#" role="button"><span>Npay</span> 구매하기</a>')
        self.assertIsNotNone(adapter.purchase_button())
        self.assertEqual(adapter.purchase_status,'인식됨')

    def test_disabled_purchase_refused(self):
        adapter=self.fixture('<a href="#" class="disabled">구매하기</a>')
        self.assertIsNone(adapter.purchase_button())
        self.assertEqual(adapter.stock(),'일시 품절')

    def test_dialog_blocks_underlying_purchase(self):
        adapter=self.fixture('<button>구매하기</button><section role="dialog"><p>로그인 필요</p></section>')
        self.assertIsNone(adapter.purchase_button())

    def test_scrolls_to_actual_buy_button(self):
        adapter=self.fixture('<div style="height:2000px">상세 설명</div><a href="#">Npay 구매하기</a>')
        self.assertIsNotNone(adapter.reveal_purchase(lambda:None))
        self.assertGreater(self.page.evaluate('scrollY'),0)

    def test_custom_dependent_groups(self):
        page='''<button aria-haspopup="listbox" aria-controls="color" onclick="document.querySelector('#color').hidden=false">색상 선택</button>
<div id="color" role="listbox" hidden><a role="option" href="#" onclick="document.querySelector('#color').hidden=true;document.querySelector('#size-open').disabled=false;return false">블랙</a></div>
<button id="size-open" aria-haspopup="listbox" aria-controls="size" disabled onclick="document.querySelector('#size').hidden=false">사이즈 선택</button>
<div id="size" role="listbox" hidden><a role="option" href="#" onclick="document.querySelector('#size').hidden=true;return false">XL</a></div>
<input title="수량" value="1"><a role="button" href="#" onclick="window.orders=(window.orders||0)+1;return false">Npay 구매하기</a>'''
        adapter=self.fixture(page)
        values=settings(quantity=2,option_groups=(OptionSpec('블랙'),OptionSpec('XL')))
        self.assertEqual(len(adapter.groups()),2)
        self.assertTrue(adapter.prepare(values,OneShot(),lambda:None))
        self.assertEqual(adapter.selected_options,['블랙','XL'])
        self.assertEqual(self.page.evaluate('window.orders'),1)

    def test_disabled_css_module_purchase_refused(self):
        adapter=self.fixture('<a href="#" class="Product_disabled_abcd">구매하기</a>')
        self.assertIsNone(adapter.purchase_button())
