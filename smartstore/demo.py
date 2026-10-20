"""An entirely local, explicitly labelled shopping and payment practice flow."""
from html import escape
from urllib.parse import urlsplit, parse_qs
import json
from .rules import defaults, CARDS

DEMO_URL = 'https://practice.invalid/products/1'


def product_html(settings, stocked):
    if settings.no_options or len(settings.groups)>1:
        return grouped_product_html(settings,stocked)
    labels = ['화이트','블랙'] if settings.option.strip() in {'화이트','블랙'} else [settings.option]
    buttons = ''.join(
        '<button role="option" onclick="choose(this.textContent)">'+escape(label)+'</button>'
        for label in labels)
    disabled = '' if stocked else 'disabled'
    stock = '구매가능' if stocked else '일시 품절'
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8">
<title>연습 상점 — 실제 주문 없음</title>
<style>body{{font:18px sans-serif;max-width:800px;margin:50px auto}}button,input{{font:inherit;padding:12px;margin:8px}}header{{background:#fff2b3;padding:20px}}[hidden]{{display:none}}</style>
<header>연습 모드 · 실제 상품/주문/결제가 아닙니다.</header>
<h1>연습 상품</h1><p>{stock}</p><p>상품 단가 40,000원 · 배송비 3,000원</p>
<button onclick="document.querySelector('#options').hidden=false">옵션 선택</button>
<section id="options" hidden>{buttons}</section>
<p id="chosen"></p><input id="qty" title="수량" aria-label="수량" type="number" value="1" hidden>
<button {disabled} onclick="location.href='/order?quantity='+document.querySelector('#qty').value+'&option='+encodeURIComponent(document.querySelector('#chosen').textContent)">구매하기</button>
<script>function choose(text){{document.querySelector('#options').hidden=true;document.querySelector('#chosen').textContent=text;document.querySelector('#qty').hidden=false}}</script>
</html>'''


def grouped_product_html(settings,stocked):
    selects=[]
    for index,spec in enumerate(settings.groups):
        labels=(['화이트','블랙'] if index==0 and spec.query in {'화이트','블랙'} else
                ['S','M','L','XL'] if index==1 else [spec.query or f'옵션 {index+1} A'])
        choices=''.join(f'<option value="{escape(label,quote=True)}">{escape(label)}</option>' for label in labels)
        selects.append(f'<label>옵션 {index+1} <select aria-label="옵션 {index+1}"><option value="" disabled selected>선택</option>{choices}</select></label>')
    controls=''.join(selects)
    disabled='' if stocked else 'disabled'
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8"><title>연습 상점 — 실제 주문 없음</title>
<body style="font:20px sans-serif;margin:40px"><h1>연습 모드 · 실제 결제 없음</h1>
<p>{'구매가능' if stocked else '일시 품절'}</p>{controls}
<label>수량 <input id="qty" title="수량" value="1" type="number"></label>
<a role="button" href="#" aria-disabled="{'false' if stocked else 'true'}" onclick="if(this.getAttribute('aria-disabled')==='true')return false;location.href='/order?quantity='+document.querySelector('#qty').value+'&options='+encodeURIComponent(JSON.stringify(Array.from(document.querySelectorAll('select')).map(e=>e.options[e.selectedIndex].text)));return false">Npay 구매하기</a>
</body></html>'''


def order_html(quantity, settings=None, option=None):
    settings = settings or defaults()
    option = option if option is not None else settings.option
    options=option if isinstance(option,(list,tuple)) else ([option] if option else [])
    option_html=''.join(f'<p>{escape(label)}</p>' for label in options)
    total = 40000 * quantity + 3000
    cards = ''.join('<label><input type="radio" name="card" '+('checked ' if i==0 else '')+
                    '>'+escape(card)+'</label><br>' for i,card in enumerate(CARDS))
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8"><title>연습 주문 화면</title>
<body style="font:18px sans-serif;margin:50px"><header>연습 모드 · 실제 결제 없음</header>
<h1>연습 주문 화면</h1>
<article><a href="{escape(settings.url,quote=True)}">연습 상품</a>{option_html}<p>수량 {quantity}개</p></article>
<label>Npay 포인트 사용 <input id="points" type="number" value="0" oninput="update()"></label>
<label><input id="all" type="checkbox" onchange="document.querySelector('#points').value=this.checked?10000:0;update()">포인트 전액사용</label>
<p>연습용 보유 포인트 10,000원</p>
{cards}<label><input type="radio" name="delivery" checked>택배</label>
<p id="total">총 결제 금액 {total:,}원</p>
<button id="pay" onclick="window.payClicks=(window.payClicks||0)+1;document.querySelector('#auth').hidden=false">{total:,}원 결제하기</button>
<section id="auth" hidden><label>결제 비밀번호 <input type="password" id="password"></label>
<button onclick="window.authClicks=(window.authClicks||0)+1;document.querySelector('#result').textContent='연습 결제 흐름 완료 (실제 결제 없음)'">결제 비밀번호 확인</button></section><p id="result"></p>
<script>function update(){{const p=Number(document.querySelector('#points').value)||0;const n=Math.max(0,{total}-p);document.querySelector('#total').textContent='총 결제 금액 '+n.toLocaleString('en-US')+'원';document.querySelector('#pay').textContent=n.toLocaleString('en-US')+'원 결제하기'}}</script>
</body></html>'''


class DemoStore:
    def __init__(self, settings):
        self.settings, self.visits = settings, 0

    def handle(self, route):
        u = urlsplit(route.request.url)
        if u.hostname != 'practice.invalid':
            route.abort()
            return
        if u.path == '/products/1':
            self.visits += 1
            content = product_html(self.settings, self.visits >= 3)
        elif u.path == '/order':
            query = parse_qs(u.query)
            quantity = int(query.get('quantity', ['1'])[0])
            option = (json.loads(query['options'][0]) if 'options' in query else
                      query.get('option', [self.settings.option])[0])
            content = order_html(quantity,self.settings,option)
        else:
            route.fulfill(status=404, body='Not found')
            return
        route.fulfill(body=content, content_type='text/html; charset=utf-8')
