import json
import os
from pathlib import Path
from datetime import datetime
from queue import Queue, Empty
from threading import Event, Thread
import time
import tkinter as tk
from tkinter import ttk, messagebox
from .rules import validate, watch_time, OneShot
from .browser import prepare_order, NeedsReview
from .hotkeys import WindowsHotkeys


class Stopped(Exception):
    pass


class Worker(Thread):
    def __init__(self, values, directory, emit):
        super().__init__(daemon=True)
        self.v, self.directory, self.emit = values, directory, emit
        self.stop = Event()
        self.pause = Event()
        self.arm = Event()
        self.review = False

    def check(self):
        while True:
            if self.stop.is_set():
                raise Stopped()
            if not self.pause.is_set():
                return
            self.stop.wait(.1)

    def delay(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.check()
            self.stop.wait(min(.1, max(0, end - time.monotonic())))

    def run(self):
        from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout
        latch = OneShot()
        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(str(self.directory / 'browser-profile'),
                    headless=False, locale='ko-KR', timezone_id='Asia/Seoul', viewport={'width':1280,'height':900})
                page = context.pages[0] if context.pages else context.new_page()
                try:
                    page.goto(self.v['url'], wait_until='domcontentloaded', timeout=20000)
                    self.emit('ready', '브라우저에서 로그인 후 상품 화면으로 돌아와 F8을 누르세요.')
                    failures = 0
                    while True:
                        self.check()
                        if not self.arm.is_set() or datetime.now() < watch_time(self.v['opening']):
                            page.wait_for_timeout(100)
                            continue
                        try:
                            started = time.monotonic()
                            response = page.reload(wait_until='domcontentloaded', timeout=15000)
                            self.check()
                            status = response.status if response else None
                            if status in {401,403,429}:
                                raise NeedsReview(f'접근 제한({status}): 자동화를 중단했습니다.')
                            if status is None or status >= 400:
                                failures += 1
                            else:
                                self.emit('log', f'응답 {time.monotonic()-started:.2f}초 · 재고 확인')
                                if prepare_order(page, self.v, latch, self.check):
                                    self.emit('log', f"배송비 포함 {self.v['limit']:,}원 이하인지, 카드·택배·옵션·수량을 직접 확인 후 결제하세요.")
                                    break
                                failures = 0
                        except BrowserTimeout:
                            if latch.used:
                                raise NeedsReview('주문 화면 진입 결과 불확실: 재시도하지 않습니다. 주문 내역을 확인하세요.')
                            failures += 1
                        if failures >= 5:
                            raise NeedsReview('연속 오류 5회: 자동화를 중단했습니다.')
                        self.delay(min(60, self.v['interval'] * 2 ** failures))
                except NeedsReview as exc:
                    self.emit('log', str(exc))
                self.review = True
                self.pause.clear()
                self.emit('review', '자동화 정지 · 브라우저 수동 확인 · F10 종료')
                try:
                    while not page.is_closed():
                        self.check()
                        page.wait_for_timeout(100)
                finally:
                    context.close()
        except Stopped:
            self.emit('log', '중지 완료. 이미 진행된 클릭이나 주문은 취소되지 않습니다.')
        except Exception as exc:
            self.emit('log', f'{type(exc).__name__}: {exc}')
        finally:
            self.emit('done', '자동화 종료')


class App:
    def __init__(self, root):
        self.root, self.worker, self.hotkeys = root, None, None
        self.events = Queue()
        self.directory = Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'SmartStoreAssistant'
        self.config = self.directory / 'settings.json'
        root.title('스마트스토어 재입고 구매 도우미')
        root.geometry('850x760')
        panel = ttk.Frame(root, padding=18)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='재입고 감시 · 주문 화면 진입', font=('맑은 고딕',16,'bold')).pack(anchor='w')
        ttk.Label(panel, text='최종 결제와 배송비 포함 한도 금액 확인은 직접 진행합니다.').pack(anchor='w', pady=10)
        defaults = dict(url='https://brand.naver.com/skinfood/products/13763129062',
            option='감자 수딩 패드 60매(+마스크팩2매)', quantity='1', limit='50000',
            opening=datetime.now().strftime('%Y-%m-%d')+' 10:00:00', interval='2', payment='카드', delivery='택배')
        try:
            saved = json.loads(self.config.read_text(encoding='utf-8'))
            if isinstance(saved, dict):
                defaults.update({k:str(v) for k,v in saved.items() if k in defaults})
        except (OSError,ValueError):
            pass
        form = ttk.Frame(panel)
        form.pack(fill='x')
        self.fields = {}
        labels = [('url','제품 링크'),('option','정확한 제품 옵션'),('quantity','제품 수량'),
            ('limit','한도 금액 (원, 수동 확인)'),('opening','오픈 날짜·시각 (한국시간)'),
            ('interval','새로고침 간격 (1~60초)'),('payment','결제 방법'),('delivery','배송 방법')]
        for row,(key,label) in enumerate(labels):
            ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',padx=(0,12),pady=6)
            var = tk.StringVar(value=defaults[key])
            self.fields[key]=var
            ttk.Entry(form,textvariable=var,state='readonly' if key in {'payment','delivery'} else 'normal').grid(row=row,column=1,sticky='ew',pady=6)
        form.columnconfigure(1,weight=1)
        ttk.Label(panel,text='오픈 1분 전부터 감시합니다. PC를 한국시간으로 설정하세요.\n0.1초 입장 시점은 보장하지 않습니다. 카드·택배는 결제 화면에서 직접 선택합니다.').pack(anchor='w',pady=10)
        buttons=ttk.Frame(panel)
        buttons.pack(fill='x')
        self.open_button=ttk.Button(buttons,text='① 저장·브라우저 열기',command=self.open)
        self.open_button.pack(side='left',padx=4)
        self.arm_button=ttk.Button(buttons,text='② 시작 F8',command=self.arm,state='disabled')
        self.arm_button.pack(side='left',padx=4)
        ttk.Button(buttons,text='일시정지 F9',command=self.pause).pack(side='left',padx=4)
        ttk.Button(buttons,text='중지 F10',command=self.stop).pack(side='left',padx=4)
        self.status=tk.StringVar(value='대기 · 오픈 날짜를 반드시 확인하세요.')
        ttk.Label(panel,textvariable=self.status,wraplength=790).pack(anchor='w',pady=10)
        self.logs=tk.Text(panel,height=12,state='disabled',wrap='word')
        self.logs.pack(fill='both',expand=True)
        if os.name=='nt':
            self.hotkeys=WindowsHotkeys(self.emit)
            self.hotkeys.start()
        else:
            for key,fn in [('<F8>',self.arm),('<F9>',self.pause),('<F10>',self.stop)]:
                root.bind(key,lambda event,action=fn:action())
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(100,self.poll)

    def emit(self,kind,value):
        self.events.put((kind,value))

    def open(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            values=validate({k:v.get().strip() for k,v in self.fields.items()})
            if datetime.strptime(values['opening'],'%Y-%m-%d %H:%M:%S')<=datetime.now():
                if not messagebox.askyesno('오픈 시각 확인','오픈 시각이 지났습니다. 지금부터 감시할까요?'):
                    return
            self.directory.mkdir(parents=True,exist_ok=True)
            temporary=self.config.with_suffix('.tmp')
            temporary.write_text(json.dumps(values,ensure_ascii=False,indent=2),encoding='utf-8')
            temporary.replace(self.config)
            self.worker=Worker(values,self.directory,self.emit)
            self.open_button.configure(state='disabled')
            self.worker.start()
        except (ValueError,OSError) as exc:
            messagebox.showerror('설정 확인',str(exc))

    def arm(self):
        if self.worker and self.worker.is_alive() and str(self.arm_button['state'])!='disabled':
            self.worker.arm.set()
            self.arm_button.configure(state='disabled')
            self.status.set('감시 예약됨 · F9 일시정지 · F10 중지')

    def pause(self):
        if self.worker and self.worker.is_alive() and not self.worker.review:
            if self.worker.pause.is_set():
                self.worker.pause.clear()
                self.status.set('감시 재개')
            else:
                self.worker.pause.set()
                self.status.set('일시정지 · F9 재개')

    def stop(self):
        if self.worker:
            self.worker.stop.set()
            self.status.set('중지 요청됨 · 진행 중인 요청 종료 후 닫힙니다.')

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='hotkey':
                    {1:self.arm,2:self.pause,3:self.stop}[value]()
                    continue
                self.logs.configure(state='normal')
                self.logs.insert('end',f'{datetime.now():%H:%M:%S} {value}\n')
                self.logs.see('end')
                self.logs.configure(state='disabled')
                if kind!='log':
                    self.status.set(value)
                if kind=='ready':
                    self.arm_button.configure(state='normal')
                elif kind=='review':
                    self.arm_button.configure(state='disabled')
                    self.root.bell()
                elif kind=='done':
                    self.open_button.configure(state='normal')
                    self.arm_button.configure(state='disabled')
        except Empty:
            pass
        self.root.after(100,self.poll)

    def close(self):
        self.stop()
        if self.worker and self.worker.is_alive():
            self.root.after(100,self.close)
        else:
            if self.hotkeys:
                self.hotkeys.stop()
            self.root.destroy()


if __name__=='__main__':
    root=tk.Tk()
    App(root)
    root.mainloop()
