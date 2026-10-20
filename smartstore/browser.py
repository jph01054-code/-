"""Product controls with native and accessible custom option-group support."""
import json
import re
from .rules import option_pattern, same_product

BUY_NAME=re.compile(r'^(?:(?:N\s*pay|네이버\s*페이)\s*)?(?:구매\s*하기|바로\s*구매)$',re.I)
OPTION_NAME=re.compile(r'^(?:(?:상품|제품)\s*)?옵션(?:\s*\d+)?(?:\s*\(필수\))?(?:\s*선택)?$|^선택$|^(?:색상|사이즈)(?:\s*선택)?$')


class NeedsReview(RuntimeError):
    pass


class OptionChoiceRequired(NeedsReview):
    def __init__(self,index,message):
        super().__init__(message)
        self.index=index


def unique(locator):
    found=[locator.nth(i) for i in range(locator.count()) if locator.nth(i).is_visible()]
    return found[0] if len(found)==1 else None


def normalized(text):
    return ''.join(text.split()).casefold()


def resolve_option(query,labels,selected=''):
    matches=[label for label in labels if normalized(label)==normalized(selected)] if selected else [
        label for label in labels if query.strip() and normalized(query) in normalized(label)]
    if len(matches)!=1:
        raise NeedsReview('옵션 검색 결과가 없거나 여러 개입니다. 해당 옵션 그룹에서 하나를 선택하세요.')
    return matches[0]


class OptionGroup:
    def __init__(self,page,opener,index,total):
        self.page,self.opener,self.index,self.total=page,opener,index,total
        self.native=opener.evaluate('(e)=>e.tagName.toLowerCase()==="select"')
        self.name=(opener.get_attribute('aria-label') or opener.get_attribute('title') or
                   ('' if self.native else opener.inner_text())).strip() or f'옵션 {index+1}'

    def choices(self,check):
        if self.native:
            choices=self.opener.locator('option')
            return [choices.nth(i) for i in range(choices.count())
                    if choices.nth(i).inner_text().strip() and not re.match(
                        r'^(?:선택(?:하세요|해|$)|옵션을?\s*선택)',choices.nth(i).inner_text().strip())]
        if not self.opener.is_enabled() or self.opener.get_attribute('aria-disabled')=='true':
            return []
        controls=self.opener.get_attribute('aria-controls')
        popup=self.page.locator('[id='+json.dumps(controls)+']') if controls else None
        visible=popup is not None and popup.count()==1 and popup.is_visible()
        if not visible:
            check()
            self.opener.click(timeout=3000)
        if popup is None:
            boxes=self.page.get_by_role('listbox')
            popup=unique(boxes)
        if popup is not None and popup.count()==1 and popup.is_visible():
            for selector in ('[role="option"]','button,a','li'):
                candidates=popup.locator(selector)
                found=[candidates.nth(i) for i in range(candidates.count()) if candidates.nth(i).is_visible()]
                if found:
                    return found
        # Older one-group layouts often omit listbox but expose option roles.
        if self.total==1:
            choices=self.page.get_by_role('option')
            return [choices.nth(i) for i in range(choices.count()) if choices.nth(i).is_visible()]
        return []

    def close(self,check):
        if not self.native:
            check()
            self.page.keyboard.press('Escape')


class StorePage:
    def __init__(self,page,target):
        self.page,self.target=page,target
        self.selected_option=''
        self.selected_options=[]
        self.option_sold_out=False
        self.purchase_status='미인식'

    def assert_product(self):
        if not same_product(self.page.url,self.target):
            raise NeedsReview('지정 상품 화면이 아닙니다. 로그인 또는 리디렉션을 확인하세요.')

    def groups(self):
        self.assert_product()
        candidates=self.page.locator(
            'select,[role="combobox"],[aria-haspopup="listbox"],button[aria-controls],[role="button"][aria-controls]'
        ).or_(self.page.get_by_role('button',name=OPTION_NAME)).or_(
            self.page.get_by_role('link',name=OPTION_NAME))
        openers=[]
        for i in range(candidates.count()):
            node=candidates.nth(i)
            if not node.is_visible():
                continue
            native=node.evaluate('(e)=>e.tagName.toLowerCase()==="select"')
            label=(node.get_attribute('aria-label') or node.get_attribute('title') or
                   node.get_attribute('name') or ('' if native else node.inner_text()))
            if re.search(r'정렬|리뷰|추천순|최신순|배송|수량|언어|quantity|qty|sort|delivery|language',label,re.I):
                continue
            openers.append(node)
        return [OptionGroup(self.page,node,i,len(openers)) for i,node in enumerate(openers)]

    def group_snapshot(self,check):
        groups=self.groups()
        result=[]
        for group in groups:
            labels=[choice.inner_text().strip() for choice in group.choices(check)]
            result.append(dict(index=group.index,name=group.name,labels=labels))
            group.close(check)
        return result

    def options(self,check):
        groups=self.groups()
        return groups[0].choices(check) if groups else []

    def stock(self):
        if self.purchase_button() is not None:
            return '구매가능'
        sold=self.page.get_by_text(re.compile(r'^(일시\s*품절|품절|SOLD OUT)(?:\s*\(.*\))?$',re.I))
        if any(sold.nth(i).is_visible() for i in range(sold.count())) or self.purchase_status=='비활성':
            return '일시 품절'
        return '확인 필요'

    def purchase_button(self):
        self.assert_product()
        candidates=self.page.get_by_role('button',name=BUY_NAME).or_(self.page.get_by_role('link',name=BUY_NAME))
        # Some Naver links expose only visible text rather than a link role.
        candidates=candidates.or_(self.page.locator('a').filter(has_text=BUY_NAME))
        buttons=[]
        disabled=False
        dialogs=self.page.get_by_role('dialog')
        active_dialog=any(dialogs.nth(i).is_visible() for i in range(dialogs.count()))
        for i in range(candidates.count()):
            node=candidates.nth(i)
            if not node.is_visible():
                continue
            if active_dialog and not node.evaluate(
                    '(e)=>!!e.closest("[role=dialog],dialog")'):
                continue
            css=(node.get_attribute('class') or '').split()
            blocked=(not node.is_enabled() or node.get_attribute('disabled') is not None or
                     node.get_attribute('aria-disabled')=='true' or
                     node.get_attribute('data-disabled')=='true' or
                     node.evaluate('(e)=>getComputedStyle(e).pointerEvents==="none"') or
                     any(re.search(r'(?:^|[_-])(?:disabled|soldout)(?:[_-]|$)',x,re.I) for x in css))
            if blocked:
                disabled=True
            else:
                buttons.append(node)
        if len(buttons)>1:
            viewport=self.page.evaluate('({width:innerWidth,height:innerHeight})')
            in_view=[]
            for button in buttons:
                box=button.bounding_box()
                if box and box['x']<viewport['width'] and box['y']<viewport['height'] and box['x']+box['width']>0 and box['y']+box['height']>0:
                    in_view.append(button)
            if len(in_view)==1:
                buttons=in_view
        self.purchase_status='인식됨' if len(buttons)==1 else ('중복 확인 필요' if len(buttons)>1 else ('비활성' if disabled else '미인식'))
        return buttons[0] if len(buttons)==1 else None

    def reveal_purchase(self,check):
        button=self.purchase_button()
        if button is not None:
            check()
            button.scroll_into_view_if_needed(timeout=3000)
        return button

    def prepare(self,settings,latch,check):
        self.option_sold_out=False
        if self.purchase_button() is None:
            return False
        groups=self.groups()
        if settings.no_options:
            if groups:
                raise NeedsReview('옵션 없음이 체크되어 있지만 실제 상품에 옵션이 있습니다.')
        elif not groups:
            raise OptionChoiceRequired(-1,'옵션을 찾지 못했습니다. 옵션 없는 상품인지 확인하고 옵션 없음을 체크하세요.')
        elif len(groups)!=len(settings.groups):
            raise OptionChoiceRequired(min(len(groups),len(settings.groups)),
                                       f'실제 옵션 {len(groups)}개에 맞춰 각 옵션의 검색 문구를 입력하세요.')
        selected=[]
        for index,spec in enumerate(settings.groups):
            # Earlier selections can unlock or replace dependent groups.
            groups=self.groups()
            if index>=len(groups):
                raise NeedsReview('옵션 선택 중 그룹 구성이 변경되었습니다.')
            group=groups[index]
            choices=group.choices(check)
            labels=[choice.inner_text().strip() for choice in choices]
            try:
                label=resolve_option(spec.query,labels,spec.selected)
            except NeedsReview as exc:
                raise OptionChoiceRequired(index,f'옵션 {index+1}: {exc}') from exc
            choice=choices[labels.index(label)]
            if not choice.is_enabled() or choice.get_attribute('aria-disabled')=='true' or re.search(r'품절|sold\s*out',label,re.I):
                self.option_sold_out=True
                group.close(check)
                return False
            check()
            if group.native:
                group.opener.select_option(label=label,timeout=3000)
                if group.opener.locator('option:checked').inner_text().strip()!=label:
                    raise NeedsReview('옵션 선택 결과가 일치하지 않습니다.')
            else:
                choice.click(timeout=3000)
            selected.append(label)
        self.selected_options=selected
        self.selected_option=' / '.join(selected)
        quantity=unique(self.page.get_by_role('spinbutton',name=re.compile('수량')))
        if quantity is None:
            quantity=unique(self.page.locator('input[title="수량"],input[aria-label="수량"]'))
        if quantity is None:
            raise NeedsReview('수량 입력란을 식별하지 못해 중단합니다.')
        check()
        quantity.fill(str(settings.quantity),timeout=3000)
        quantity.press('Tab')
        if quantity.input_value()!=str(settings.quantity):
            raise NeedsReview('수량이 일치하지 않습니다.')
        button=self.reveal_purchase(check)
        if button is None:
            raise NeedsReview('옵션 선택 후 실제 구매 버튼을 확인하지 못했습니다.')
        check()
        latch.claim()
        button.click(timeout=10000)
        return True

    def total(self):
        self.page.get_by_text(re.compile(r'총\s*결제\s*금액')).first.wait_for(timeout=3000)
        text=self.page.locator('body').inner_text(timeout=3000)
        matches=re.findall(r'총\s*결제\s*금액\s*([\d,]+)\s*원',text)
        if len(matches)!=1 or not re.fullmatch(r'(?:\d{1,3}(?:,\d{3})+|\d+)',matches[0]):
            return None
        return int(matches[0].replace(',',''))
