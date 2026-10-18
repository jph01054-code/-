"""One browser session, with bounded polling and cooperative cancellation."""
from threading import Event, Thread
from dataclasses import replace
from queue import Queue, Empty
import time
from .rules import OneShot, now_kst, same_product
from .browser import StorePage, NeedsReview, normalized
from .demo import DemoStore, DEMO_URL
from .checkout import CheckoutPage


class Stopped(Exception):
    pass


class Expired(Exception):
    pass


class Session(Thread):
    def __init__(self, settings, directory, emit, password='', auto_start=False):
        super().__init__(daemon=True)
        self.settings = settings.validate()
        self.directory, self.emit = directory, emit
        self.stop_event, self.pause_event, self.arm_event = Event(), Event(), Event()
        self.ready_event, self.review_event = Event(), Event()
        self.deadline_at = None
        self.attempts = 0
        self.latch = OneShot()
        self.payment_latch = OneShot()
        self.password = password
        self.auto_start = auto_start
        self.option_commands = Queue()

    def choose_option(self, label):
        self.option_commands.put(label)

    def update_options(self, adapter):
        labels = [choice.inner_text().strip() for choice in adapter.options(self.check)]
        self.emit('options', labels)
        try:
            while True:
                label = self.option_commands.get_nowait()
                self.settings = replace(self.settings, selected_option=label)
        except Empty:
            pass
        return labels

    def log(self, message):
        self.emit('log', message)

    def state(self, name, message):
        self.emit('state', (name, message))

    def check(self):
        while True:
            if self.stop_event.is_set():
                raise Stopped()
            if self.deadline_at is not None and now_kst() >= self.deadline_at:
                raise Expired()
            if not self.pause_event.is_set():
                return
            self.stop_event.wait(.1)

    def idle(self, page, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.check()
            page.wait_for_timeout(min(100, max(1, (end - time.monotonic()) * 1000)))

    def arm(self):
        if not self.ready_event.is_set() or self.arm_event.is_set() or self.review_event.is_set():
            return False
        self.arm_event.set()
        return True

    def hold(self, page, message):
        self.deadline_at = None
        self.review_event.set()
        self.pause_event.clear()
        self.state('review', message)
        while not page.is_closed():
            self.check()
            page.wait_for_timeout(100)

    def monitor(self, page, target):
        from playwright.sync_api import TimeoutError as BrowserTimeout
        self.ready_event.set()
        self.state('ready', '브라우저 확인 후 감시 시작(F8)을 누르세요.')
        if self.auto_start:
            self.arm_event.set()
        while not self.arm_event.is_set():
            self.idle(page, .1)
        demo = self.settings.mode == 'demo'
        armed_at = now_kst()
        self.deadline_at = (armed_at if demo else max(self.settings.start_at, armed_at))
        from datetime import timedelta
        self.deadline_at += timedelta(minutes=self.settings.duration)
        self.state('scheduled', '연습은 바로 시작합니다.' if demo else f'감시 시작: {self.settings.start_at:%Y-%m-%d %H:%M:%S} (한국시간)')
        while not demo and now_kst() < self.settings.start_at:
            self.idle(page, .1)
        self.state('watching', '재입고 확인 중 · F9 일시정지 · F10 중지')
        adapter = StorePage(page, target)
        failures = 0
        while True:
            self.check()
            try:
                began = time.monotonic()
                response = page.reload(wait_until='domcontentloaded', timeout=15000)
                self.check()
                self.attempts += 1
                self.emit('stats', (self.attempts, time.monotonic() - began))
                status = response.status if response else None
                if status in {401, 403, 429}:
                    raise NeedsReview(f'접근 제한({status})으로 감시를 중단했습니다.')
                if status is None or status >= 400:
                    failures += 1
                    self.log(f'페이지 응답 오류({status}) · 요청 간격을 늘립니다.')
                else:
                    # Give client-rendered pages time to expose their controls.
                    self.idle(page, .4)
                    self.emit('stock', adapter.stock())
                    labels = self.update_options(adapter)
                    matches = [label for label in labels if normalized(self.settings.option) in normalized(label)]
                    if self.settings.action == 'prepare' and len(matches) > 1 and not self.settings.selected_option:
                        self.state('choice','검색된 옵션이 여러 개입니다. 화면에서 하나를 체크하세요.')
                        while not self.settings.selected_option:
                            self.idle(page,.1)
                            self.update_options(adapter)
                        self.state('watching','선택한 옵션으로 진행합니다.')
                    if self.settings.action == 'notify':
                        if adapter.purchase_button() is not None:
                            self.hold(page, '구매 버튼 감지 · 지정 옵션의 재고는 직접 확인하세요.')
                            return
                    elif adapter.prepare(self.settings, self.latch, self.check):
                        self.emit('selected', adapter.selected_option)
                        self.log('주문 화면 진입을 한 번 시도했습니다. 자동 재시도하지 않습니다.')
                        try:
                            amount = adapter.total()
                        except BrowserTimeout:
                            amount = None
                        if amount is None:
                            self.log('최종 금액을 확실히 읽지 못했습니다. 배송비 포함 금액을 직접 확인하세요.')
                        elif amount > self.settings.limit:
                            self.log(f'한도 초과: 표시 총액 {amount:,}원 / 한도 {self.settings.limit:,}원. 결제하지 마세요.')
                        else:
                            self.log(f'표시 총액 {amount:,}원 / 한도 {self.settings.limit:,}원. 할인·배송비 변경 여부도 직접 확인하세요.')
                        self.emit('amount', amount)
                        if self.settings.auto_pay:
                            checkout = CheckoutPage(page,demo=demo)
                            self.log('상품·옵션·수량·포인트·카드·배송·최종 금액을 확인합니다.')
                            try:
                                charged = checkout.submit(self.settings,adapter.selected_option,
                                                          self.payment_latch,self.check)
                                self.emit('amount',charged)
                                self.log('결제하기 버튼을 한 번 클릭했습니다. 결제 성공 여부는 주문 내역에서 확인하세요.')
                                if checkout.authenticate(self.password,self.check):
                                    self.log('지원되는 비밀번호 입력 단계를 진행했습니다. 결제 성공 여부는 직접 확인하세요.')
                                else:
                                    self.log('보안 키패드·추가 인증·팝업 또는 비밀번호 입력은 직접 확인하세요.')
                            finally:
                                self.password = ''
                            self.hold(page,'결제 버튼 클릭 후 정지 · 인증 또는 주문 내역을 확인하세요.')
                            return
                        self.hold(page, '주문 화면 확인 · 카드·택배·총액 확인과 최종 결제는 직접 진행하세요.')
                        return
                    if adapter.option_sold_out:
                        self.emit('stock','일시 품절')
                    failures = 0
            except BrowserTimeout:
                if self.payment_latch.used:
                    raise NeedsReview('결제 클릭 결과가 불확실합니다. 재시도하지 않습니다. 주문 내역을 확인하세요.')
                if self.latch.used:
                    raise NeedsReview('주문 진입 결과가 불확실합니다. 재시도하지 않고 주문 내역 확인을 기다립니다.')
                failures += 1
                self.log('화면 응답 시간 초과 · 요청 간격을 늘립니다.')
            if failures >= 5:
                raise NeedsReview('연속 오류 5회로 자동화를 중단했습니다.')
            self.idle(page, min(60, self.settings.interval * 2 ** failures))

    def run(self):
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout
            self.state('opening', '전용 브라우저를 여는 중…')
            self.directory.mkdir(parents=True, exist_ok=True)
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    str(self.directory / ('practice-profile' if self.settings.mode == 'demo' else 'live-profile')),
                    headless=False, locale='ko-KR', timezone_id='Asia/Seoul',
                    viewport={'width': 1280, 'height': 900},
                )
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    if self.settings.mode == 'demo':
                        store = DemoStore(self.settings)
                        context.route('**/*', store.handle)
                        target = DEMO_URL
                        self.log('연습 모드: 실제 네이버 접속·주문·결제는 없습니다.')
                    else:
                        target = self.settings.url
                        self.log('실제 상품 모드: 로그인 후 지정 상품으로 돌아오세요.')
                    self.check()
                    page.goto(target, wait_until='domcontentloaded', timeout=20000)
                    if same_product(page.url,target):
                        try:
                            preview = StorePage(page,target)
                            self.emit('stock',preview.stock())
                            self.update_options(preview)
                        except (NeedsReview,BrowserTimeout):
                            self.log('초기 상품 정보는 감시 시작 후 다시 확인합니다.')
                    try:
                        self.monitor(page, target)
                    except NeedsReview as exc:
                        self.log(str(exc))
                        self.hold(page, '자동화 중단 · 브라우저에서 수동 확인하세요.')
                finally:
                    context.close()
        except Stopped:
            self.log('중지 완료. 이미 진행된 클릭이나 주문은 취소되지 않습니다.')
        except Expired:
            self.log('설정한 최대 감시 시간이 지나 종료했습니다.')
        except Exception as exc:
            self.state('error', f'실행 실패: {type(exc).__name__}. 브라우저 설치와 화면 상태를 확인하세요.')
        finally:
            self.password = ''
            self.ready_event.clear()
            self.emit('done', None)
