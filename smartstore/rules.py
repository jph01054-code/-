"""Immutable settings and scheduling in Korean time."""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import math
import re
from urllib.parse import urlsplit

KST = timezone(timedelta(hours=9))
CARDS = ('현대카드', '신한카드', '농협카드', '국민카드', '네이버페이머니카드')


def now_kst():
    return datetime.now(KST)


def parse_opening(value):
    return datetime.strptime(value, '%Y-%m-%d %H:%M:%S').replace(tzinfo=KST)


@dataclass(frozen=True)
class OptionSpec:
    query: str = ''
    selected: str = ''


@dataclass(frozen=True)
class Settings:
    url: str
    option: str
    quantity: int = 1
    limit: int = 50000
    opening: str = ''
    interval: float = 2
    duration: int = 20
    mode: str = 'demo'
    action: str = 'prepare'
    payment: str = '카드'
    delivery: str = '택배'
    card: str = '현대카드'
    points_mode: str = 'none'
    points_amount: int = 0
    auto_pay: bool = False
    selected_option: str = ''
    start_time: str = ''
    no_options: bool = False
    option_groups: tuple = ()

    @classmethod
    def from_dict(cls, values):
        raw_groups=values.get('option_groups',[])
        if not isinstance(raw_groups,(tuple,list)) or any(not isinstance(group,dict) for group in raw_groups):
            raise ValueError('옵션 그룹 설정 형식이 올바르지 않습니다.')
        return cls(
            url=str(values['url']).strip(), option=str(values['option']).strip(),
            quantity=int(str(values['quantity'])), limit=int(str(values['limit']).replace(',', '')),
            opening=str(values.get('opening', values.get('start_time', ''))).strip(), interval=float(values.get('interval', 2)),
            duration=int(str(values.get('duration', 20))), mode=values.get('mode', 'demo'),
            action=values.get('action', 'prepare'), payment=values.get('payment', '카드'),
            delivery=values.get('delivery', '택배'),
            card=values.get('card', '현대카드'), points_mode=values.get('points_mode', 'none'),
            points_amount=int(str(values.get('points_amount', 0)).replace(',', '')),
            auto_pay=values.get('auto_pay', False), selected_option=str(values.get('selected_option', '')).strip(),
            start_time=str(values.get('start_time', '')).strip(),
            no_options=values.get('no_options', False),
            option_groups=tuple(OptionSpec(str(group.get('query','')).strip(),
                                          str(group.get('selected','')).strip())
                                for group in raw_groups),
        ).validate()

    def validate(self):
        u = urlsplit(self.url)
        if (u.scheme != 'https' or u.hostname not in {'brand.naver.com', 'smartstore.naver.com'}
                or u.username or u.password or u.port is not None
                or not re.fullmatch(r'/[^/]+/products/\d+/?', u.path)):
            raise ValueError('스마트스토어 HTTPS 상품 링크를 입력하세요.')
        if not isinstance(self.no_options,bool):
            raise ValueError('옵션 없음 선택값을 확인하세요.')
        if not self.no_options and not any(group.query.strip() or group.selected for group in self.groups):
            raise ValueError('옵션 문구를 입력하거나 제품 옵션 없음을 체크하세요.')
        if any(len(group.query)>500 or len(group.selected)>500 for group in self.groups):
            raise ValueError('각 옵션 문구는 500자 이내로 입력하세요.')
        if not 1 <= self.quantity <= 99 or not 1 <= self.limit <= 100_000_000:
            raise ValueError('수량 1~99, 한도 금액 1~100,000,000원으로 입력하세요.')
        if not math.isfinite(self.interval) or not .1 <= self.interval <= 5:
            raise ValueError('새로고침 간격은 0.1~5초입니다.')
        if not 1 <= self.duration <= 180:
            raise ValueError('최대 감시 시간은 1~180분입니다.')
        if self.mode not in {'demo', 'live'} or self.action not in {'notify', 'prepare'}:
            raise ValueError('실행 모드와 재입고 동작을 확인하세요.')
        if self.payment != '카드' or self.delivery != '택배':
            raise ValueError('현재 희망 조건은 카드·택배입니다.')
        if self.card not in CARDS or self.points_mode not in {'none', 'amount', 'all'}:
            raise ValueError('포인트 사용 방식과 카드를 확인하세요.')
        if not 0 <= self.points_amount <= 100_000_000:
            raise ValueError('사용할 포인트 금액을 확인하세요.')
        if self.points_mode == 'amount' and self.points_amount < 1:
            raise ValueError('사용할 포인트를 1원 이상 입력하세요.')
        if not isinstance(self.auto_pay, bool):
            raise ValueError('자동 결제 선택값이 올바르지 않습니다.')
        if self.auto_pay and self.action != 'prepare':
            raise ValueError('자동 결제에는 구매하기 선택이 필요합니다.')
        if self.start_time:
            parse_opening(self.start_time)
        parse_opening(self.opening)
        return self

    @property
    def groups(self):
        if self.no_options:
            return ()
        return self.option_groups or (OptionSpec(self.option,self.selected_option),)

    @property
    def start_at(self):
        if self.start_time:
            return parse_opening(self.start_time)
        return parse_opening(self.opening) - timedelta(minutes=1)

    def deadline(self, armed_at):
        return max(self.start_at, armed_at) + timedelta(minutes=self.duration)

    def to_dict(self):
        return asdict(self)


def defaults():
    current = now_kst()
    opening = current.replace(hour=10, minute=0, second=0, microsecond=0)
    if opening <= current:
        opening += timedelta(days=1)
    return Settings(url='https://brand.naver.com/skinfood/products/13763129062',
                    option='감자 수딩 패드 60매(+마스크팩2매)',
                    opening=opening.strftime('%Y-%m-%d %H:%M:%S'))


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
            raise RuntimeError('주문 화면 진입은 세션당 한 번만 시도합니다.')
        self.used = True
