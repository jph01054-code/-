"""Explicitly verified checkout controls; unsupported screens require the user."""
import re
from urllib.parse import urljoin, urlsplit
from .browser import NeedsReview, StorePage, unique
from .rules import same_product, option_pattern


class CheckoutPage:
    def __init__(self, page, demo=False):
        self.page, self.demo = page, demo
        self.clicked = False

    def trusted(self):
        u = urlsplit(self.page.url)
        allowed = (u.hostname == 'practice.invalid' if self.demo else
                   u.hostname == 'pay.naver.com' or bool(u.hostname and u.hostname.endswith('.pay.naver.com')))
        if not (u.scheme == 'https' and allowed and not u.username and not u.password and u.port in {None,443}):
            raise NeedsReview('확인된 네이버페이 주문 화면이 아니므로 결제를 중단합니다.')

    def verify_item(self, settings, option):
        self.trusted()
        links = self.page.locator('a[href]')
        products = []
        for i in range(links.count()):
            link = links.nth(i)
            href = urljoin(self.page.url, link.get_attribute('href') or '')
            u = urlsplit(href)
            if u.hostname in {'brand.naver.com','smartstore.naver.com'} and '/products/' in u.path and link.is_visible():
                products.append((link,href))
        if len(products) != 1 or not same_product(products[0][1],settings.url):
            raise NeedsReview('주문 상품이 한 개이며 지정한 상품인지 확인하지 못했습니다.')
        row = products[0][0].locator('xpath=ancestor::*[self::li or self::article][1]')
        if row.count() != 1 or unique(row.get_by_text(option_pattern(option))) is None:
            raise NeedsReview('주문 상품의 선택 옵션을 확인하지 못했습니다.')
        quantities = re.findall(r'수량\s*(\d+)\s*개',row.inner_text())
        if quantities != [str(settings.quantity)]:
            raise NeedsReview('주문 상품의 수량이 일치하지 않습니다.')

    @staticmethod
    def checked(control):
        return control.get_attribute('aria-checked') == 'true' or control.is_checked()

    def radio(self, name, check):
        control = unique(self.page.get_by_role('radio', name=name, exact=True))
        if control is None:
            raise NeedsReview(f'{name} 선택 항목을 확인하지 못했습니다.')
        check()
        control.click(timeout=3000)
        if not self.checked(control):
            raise NeedsReview(f'{name} 선택 결과를 확인하지 못했습니다.')

    def configure(self, settings, check):
        self.trusted()
        point_input = unique(self.page.get_by_label(re.compile(r'^\s*(Npay 포인트 사용|포인트 사용 금액)\s*$')))
        all_points = unique(self.page.get_by_role('checkbox', name=re.compile(r'^(?:Npay )?포인트 전액사용$')))
        if point_input is None or all_points is None:
            raise NeedsReview('포인트 설정을 확실히 식별하지 못했습니다.')
        wanted_all = settings.points_mode == 'all'
        if self.checked(all_points) != wanted_all:
            check()
            all_points.click(timeout=3000)
        if self.checked(all_points) != wanted_all:
            raise NeedsReview('전액사용 선택 결과가 다릅니다.')
        if not wanted_all:
            amount = settings.points_amount if settings.points_mode == 'amount' else 0
            check()
            point_input.fill(str(amount), timeout=3000)
            point_input.press('Tab')
            if point_input.input_value().replace(',','') != str(amount):
                raise NeedsReview('포인트 사용 금액이 일치하지 않습니다.')
        self.radio(settings.card, check)
        self.radio(settings.delivery, check)

    def verify_preferences(self, settings):
        for name in (settings.card, settings.delivery):
            control = unique(self.page.get_by_role('radio',name=name,exact=True))
            if control is None or not self.checked(control):
                raise NeedsReview('결제 직전 카드 또는 배송 선택이 변경되었습니다.')
        field = unique(self.page.get_by_label(re.compile(r'^\s*(Npay 포인트 사용|포인트 사용 금액)\s*$')))
        all_points = unique(self.page.get_by_role('checkbox',name=re.compile(r'^(?:Npay )?포인트 전액사용$')))
        if field is None or all_points is None or self.checked(all_points) != (settings.points_mode == 'all'):
            raise NeedsReview('결제 직전 포인트 설정이 변경되었습니다.')
        if settings.points_mode != 'all':
            amount = settings.points_amount if settings.points_mode == 'amount' else 0
            if field.input_value().replace(',','') != str(amount):
                raise NeedsReview('결제 직전 포인트 사용 금액이 다릅니다.')

    def submit(self, settings, option, latch, check):
        self.verify_item(settings,option)
        self.configure(settings,check)
        # Require a stable, explicit amount and an exactly matching payment button.
        amount = StorePage(self.page,settings.url).total()
        self.page.wait_for_timeout(500)
        if amount is None or amount != StorePage(self.page,settings.url).total() or not 0 <= amount <= settings.limit:
            raise NeedsReview('최종 금액이 불명확하거나 한도를 초과해 결제하지 않습니다.')
        name = re.compile(r'^([\d,]+)\s*원\s*결제하기$')
        button = unique(self.page.get_by_role('button',name=name))
        if button is None or not button.is_enabled():
            raise NeedsReview('금액이 표시된 결제하기 버튼을 확인하지 못했습니다.')
        button_amount = int(re.fullmatch(name,button.inner_text().strip()).group(1).replace(',',''))
        if button_amount != amount:
            raise NeedsReview('총액과 결제 버튼의 금액이 다릅니다.')
        self.verify_item(settings,option)
        self.verify_preferences(settings)
        check()
        if StorePage(self.page,settings.url).total() != amount:
            raise NeedsReview('결제 직전 금액이 변경되어 중단합니다.')
        latch.claim()
        self.clicked = True
        button.click(timeout=10000)
        return amount

    def authenticate(self, password, check):
        """Only standard labelled fields on trusted pages; no keypad bypass."""
        self.trusted()
        field = unique(self.page.get_by_label('결제 비밀번호',exact=True))
        confirm = unique(self.page.get_by_role('button',name='결제 비밀번호 확인',exact=True))
        if not password or field is None or confirm is None:
            return False
        if field.get_attribute('type') != 'password' or not field.is_editable():
            return False
        try:
            check()
            self.trusted()
            field.fill(password,timeout=3000)
            check()
            confirm.click(timeout=3000)
            return True
        except Exception as exc:
            # Never surface Playwright call logs which could include fill values.
            from .session import Stopped, Expired
            if isinstance(exc,(Stopped,Expired)):
                raise
            return False
