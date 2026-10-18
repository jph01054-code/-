import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit


def validate(values):
    v = dict(values)
    u = urlsplit(v['url'])
    if (u.scheme != 'https' or u.hostname not in {'brand.naver.com', 'smartstore.naver.com'}
            or u.username or u.password or u.port is not None
            or not re.fullmatch(r'/[^/]+/products/\d+/?', u.path)):
        raise ValueError('네이버 스마트스토어 HTTPS 상품 링크를 입력하세요.')
    v['quantity'] = int(v['quantity'])
    v['limit'] = int(str(v['limit']).replace(',', ''))
    v['interval'] = float(v['interval'])
    if not 1 <= v['quantity'] <= 99 or v['limit'] <= 0 or not 1 <= v['interval'] <= 60:
        raise ValueError('수량 1~99, 금액 1원 이상, 간격 1~60초로 입력하세요.')
    if not v['option'].strip():
        raise ValueError('정확한 옵션을 입력하세요.')
    datetime.strptime(v['opening'], '%Y-%m-%d %H:%M:%S')
    return v


def watch_time(value):
    return datetime.strptime(value, '%Y-%m-%d %H:%M:%S') - timedelta(minutes=1)


def option_pattern(value):
    return re.compile(r'^\s*' + r'\s*'.join(re.escape(c) for c in value if not c.isspace()) + r'\s*$')


def same_product(current, target):
    a, b = urlsplit(current), urlsplit(target)
    return (a.scheme == 'https' and a.hostname == b.hostname and not a.username
            and not a.password and a.port in {None, 443}
            and a.path.rstrip('/') == b.path.rstrip('/'))


class OneShot:
    def __init__(self):
        self.used = False

    def claim(self):
        if self.used:
            raise RuntimeError('중복 주문 진입을 중단합니다.')
        self.used = True
