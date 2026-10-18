"""DOM adapter; final payment authorization is outside its supported actions."""
import re
from .rules import option_pattern, same_product


class NeedsReview(RuntimeError):
    pass


def unique(locator):
    found = [locator.nth(i) for i in range(locator.count()) if locator.nth(i).is_visible()]
    return found[0] if len(found) == 1 else None


def normalized(text):
    return ''.join(text.split()).casefold()


def resolve_option(query, labels, selected=''):
    if selected:
        matches = [label for label in labels if normalized(label) == normalized(selected)]
    else:
        matches = [label for label in labels if normalized(query) in normalized(label)]
    if len(matches) != 1:
        raise NeedsReview('옵션 검색 결과가 없거나 여러 개입니다. 옵션 목록에서 하나를 선택하세요.')
    return matches[0]


class StorePage:
    def __init__(self, page, target):
        self.page, self.target = page, target
        self.selected_option = ''
        self.option_sold_out = False

    def options(self, check):
        choices = self.page.get_by_role('option')
        visible = [choices.nth(i) for i in range(choices.count()) if choices.nth(i).is_visible()]
        if not visible:
            dropdown = unique(self.page.get_by_role('button', name=re.compile(r'^(선택|옵션 선택)\s*$')))
            if dropdown is None:
                dropdown = unique(self.page.get_by_role('combobox'))
            if dropdown is None or not dropdown.is_enabled():
                return []
            check()
            dropdown.click(timeout=3000)
            visible = [choices.nth(i) for i in range(choices.count()) if choices.nth(i).is_visible()]
        return visible

    def stock(self):
        if self.purchase_button() is not None:
            return '구매가능'
        sold = self.page.get_by_text(re.compile(r'^(일시\s*품절|품절|SOLD OUT)(?:\s*\(.*\))?$', re.I))
        if any(sold.nth(i).is_visible() for i in range(sold.count())):
            return '일시 품절'
        return '확인 필요'

    def purchase_button(self):
        if not same_product(self.page.url, self.target):
            raise NeedsReview('지정 상품 화면이 아닙니다. 로그인 또는 리디렉션을 확인하세요.')
        name = re.compile(r'^(구매하기|바로구매|바로 구매)$')
        candidates = self.page.get_by_role('button', name=name).or_(self.page.get_by_role('link', name=name))
        button = unique(candidates)
        if button is None or not button.is_enabled() or button.get_attribute('aria-disabled') == 'true':
            return None
        return button

    def prepare(self, settings, latch, check):
        self.option_sold_out = False
        if self.purchase_button() is None:
            return False
        choices = self.options(check)
        if not choices:
            raise NeedsReview('옵션 선택 목록을 식별하지 못했습니다.')
        labels = [choice.inner_text().strip() for choice in choices]
        label = resolve_option(settings.option, labels, settings.selected_option)
        choice = choices[labels.index(label)]
        if not choice.is_enabled() or choice.get_attribute('aria-disabled') == 'true':
            self.option_sold_out = True
            return False
        if re.search(r'품절|sold\s*out', label, re.I):
            self.option_sold_out = True
            return False
        check()
        choice.click(timeout=3000)
        self.selected_option = label
        quantity = unique(self.page.get_by_role('spinbutton', name=re.compile('수량')))
        if quantity is None:
            quantity = unique(self.page.locator('input[title="수량"],input[aria-label="수량"]'))
        if quantity is None:
            raise NeedsReview('수량 입력란을 식별하지 못해 중단합니다.')
        check()
        quantity.fill(str(settings.quantity), timeout=3000)
        quantity.press('Tab')
        if quantity.input_value() != str(settings.quantity):
            raise NeedsReview('수량이 일치하지 않습니다.')
        check()
        button = self.purchase_button()
        if button is None:
            raise NeedsReview('옵션 선택 후 구매 버튼을 확인하지 못했습니다.')
        latch.claim()
        button.click(timeout=10000)
        return True

    def total(self):
        self.page.get_by_text(re.compile(r'총\s*결제\s*금액')).first.wait_for(timeout=3000)
        text = self.page.locator('body').inner_text(timeout=3000)
        matches = re.findall(r'총\s*결제\s*금액\s*([\d,]+)\s*원', text)
        if len(matches) != 1 or not re.fullmatch(r'(?:\d{1,3}(?:,\d{3})+|\d+)', matches[0]):
            return None
        return int(matches[0].replace(',', ''))
