import re
from .rules import option_pattern, same_product


class NeedsReview(RuntimeError):
    pass


def unique(locator):
    found = [locator.nth(i) for i in range(locator.count()) if locator.nth(i).is_visible()]
    return found[0] if len(found) == 1 else None


def prepare_order(page, v, latch, check):
    if not same_product(page.url, v['url']):
        raise NeedsReview('지정 상품 화면이 아닙니다. 로그인·상품 링크를 확인하세요.')
    name = re.compile(r'^(구매하기|바로구매|바로 구매)$')
    buy = unique(page.get_by_role('button', name=name))
    if buy is None:
        buy = unique(page.get_by_role('link', name=name))
    if buy is None or not buy.is_enabled() or buy.get_attribute('aria-disabled') == 'true':
        return False
    pattern = option_pattern(v['option'])
    choice = unique(page.get_by_role('option', name=pattern))
    if choice is None:
        dropdown = unique(page.get_by_role('button', name=re.compile(r'^(선택|옵션 선택)\s*$')))
        if dropdown is None:
            dropdown = unique(page.get_by_role('combobox'))
        if dropdown is None:
            raise NeedsReview('옵션 선택 영역을 식별하지 못했습니다. 수동 확인이 필요합니다.')
        check()
        dropdown.click(timeout=3000)
        choice = unique(page.get_by_role('option', name=pattern))
        if choice is None:
            choice = unique(page.get_by_text(pattern))
    if choice is None:
        sold = re.compile(pattern.pattern.removesuffix(r'\s*$') + r'\s*\(?(?:일시\s*품절|품절)\)?\s*$')
        if unique(page.get_by_text(sold)) is not None:
            return False
        raise NeedsReview('지정 옵션과 정확히 일치하는 선택지를 찾지 못했습니다.')
    if not choice.is_enabled() or choice.get_attribute('aria-disabled') == 'true':
        return False
    check()
    choice.click(timeout=3000)
    quantity = unique(page.get_by_role('spinbutton', name=re.compile('수량')))
    if quantity is None:
        quantity = unique(page.locator('input[title="수량"],input[aria-label="수량"]'))
    if quantity is None:
        raise NeedsReview('수량 입력란을 식별하지 못해 중단합니다.')
    check()
    quantity.fill(str(v['quantity']), timeout=3000)
    quantity.press('Tab')
    if quantity.input_value() != str(v['quantity']):
        raise NeedsReview('수량 확인에 실패했습니다.')
    check()
    latch.claim()
    # A timeout can follow a successful click. The caller must not retry this.
    buy.click(timeout=10000)
    return True
