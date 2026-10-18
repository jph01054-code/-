"""A single, compact Windows control panel."""
from queue import Queue, Empty
import os
import tkinter as tk
from tkinter import ttk, messagebox
from .rules import Settings, now_kst, CARDS
from .storage import data_dir, load, save
from .session import Session
from .hotkeys import WindowsHotkeys
from .browser import normalized

PHASES={'idle':'OFF','opening':'브라우저 시작','ready':'준비','scheduled':'예약 대기',
        'watching':'ON · 감시 중','choice':'옵션 선택 필요','paused':'일시정지',
        'review':'직접 확인 필요','error':'오류','finished':'OFF'}


class App:
    def __init__(self,root):
        self.root,self.worker,self.hotkeys=root,None,None
        self.events=Queue()
        self.directory=data_dir()
        self.config_path=self.directory/'settings.json'
        self.phase='idle'
        self.previous_phase='watching'
        self.closing=False
        self.editors=[]
        self.option_labels=[]
        self.displayed_labels=None
        self.vars={}
        settings,warning=load(self.config_path)
        self.build(settings)
        if warning:
            self.log(warning)
        if os.name=='nt':
            self.hotkeys=WindowsHotkeys(self.emit)
            self.hotkeys.start()
        else:
            for key,fn in [('<F8>',self.turn_on),('<F9>',self.pause),('<F10>',self.stop)]:
                root.bind(key,lambda event,action=fn:action())
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(100,self.poll)

    def build(self,settings):
        root=self.root
        root.title('스마트스토어 자동 클릭')
        root.geometry('1000x860')
        root.minsize(940,820)
        style=ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame',background='#f6f8f9')
        style.configure('TLabel',background='#f6f8f9',font=('맑은 고딕',10))
        style.configure('TLabelframe',background='#f6f8f9',borderwidth=1)
        style.configure('TLabelframe.Label',background='#f6f8f9',font=('맑은 고딕',11,'bold'))
        style.configure('TCheckbutton',background='#f6f8f9',font=('맑은 고딕',10))
        style.configure('TRadiobutton',background='#f6f8f9',font=('맑은 고딕',10))
        style.configure('TButton',padding=(10,8),font=('맑은 고딕',10))
        style.configure('Title.TLabel',font=('맑은 고딕',21,'bold'),foreground='#19362c')
        style.configure('State.TLabel',font=('맑은 고딕',13,'bold'),foreground='#16854e')
        outer=ttk.Frame(root,padding=20)
        outer.pack(fill='both',expand=True)
        header=ttk.Frame(outer)
        header.pack(fill='x')
        ttk.Label(header,text='스마트스토어 자동 클릭',style='Title.TLabel').pack(side='left')
        self.on=tk.BooleanVar(value=False)
        ttk.Checkbutton(header,text='프로그램 ON / OFF',variable=self.on,command=self.toggle).pack(side='right')
        self.clock=tk.StringVar()
        ttk.Label(outer,textvariable=self.clock,foreground='#6b7785').pack(anchor='w',pady=(4,12))
        values=settings.to_dict()
        values['start_time']=settings.start_at.strftime('%Y-%m-%d %H:%M:%S')
        for key in ['url','option','quantity','limit','start_time','interval','duration','points_amount']:
            self.vars[key]=tk.StringVar(value=str(values[key]))
        self.vars['card']=tk.StringVar(value=values['card'])
        self.vars['points_mode']=tk.StringVar(value=values['points_mode'])
        self.vars['mode']=tk.StringVar(value='demo')
        self.buy=tk.BooleanVar(value=values['action']=='prepare')
        self.auto_pay=tk.BooleanVar(value=values['auto_pay'])
        self.password=tk.StringVar()
        self.selection=tk.StringVar(value=values['selected_option'])
        grid=ttk.Frame(outer)
        grid.pack(fill='x')
        grid.columnconfigure(0,weight=3)
        grid.columnconfigure(1,weight=2)
        left=ttk.LabelFrame(grid,text='상품',padding=14)
        left.grid(row=0,column=0,sticky='nsew',padx=(0,8))
        right=ttk.LabelFrame(grid,text='구매 · 결제',padding=14)
        right.grid(row=0,column=1,sticky='nsew',padx=(8,0))
        left.columnconfigure(0,weight=1)
        ttk.Label(left,text='판매 링크').grid(row=0,column=0,sticky='w')
        self.entry(left,'url',1)
        self.stock=tk.StringVar(value='확인 전')
        ttk.Label(left,text='제품 상태').grid(row=2,column=0,sticky='w',pady=(12,0))
        ttk.Label(left,textvariable=self.stock,style='State.TLabel').grid(row=3,column=0,sticky='w',pady=3)
        ttk.Label(left,text='제품 옵션 · 포함된 문구 검색 (예: 블랙)').grid(row=4,column=0,sticky='w',pady=(12,0))
        self.entry(left,'option',5)
        self.vars['option'].trace_add('write',self.search_changed)
        ttk.Label(left,text='제품 옵션 (필수) · 하나만 체크').grid(row=6,column=0,sticky='w',pady=(12,6))
        self.option_frame=ttk.Frame(left)
        self.option_frame.grid(row=7,column=0,sticky='nsew')
        self.option_note=ttk.Label(left,text='브라우저에서 읽은 옵션을 표시합니다.',foreground='#6b7785',wraplength=450)
        self.option_note.grid(row=8,column=0,sticky='w',pady=6)
        self.selected_text=tk.StringVar(value='선택: —')
        ttk.Label(left,textvariable=self.selected_text,foreground='#16854e',wraplength=450).grid(row=9,column=0,sticky='w')
        qty=ttk.Frame(left)
        qty.grid(row=10,column=0,sticky='ew',pady=(14,0))
        ttk.Label(qty,text='제품 수량').pack(side='left')
        q=ttk.Entry(qty,textvariable=self.vars['quantity'],width=7)
        q.pack(side='left',padx=12)
        self.editors.append((q,'normal'))
        ttk.Label(qty,text='개').pack(side='left')
        right.columnconfigure(0,weight=1)
        purchase=ttk.Checkbutton(right,text='구매하기 · 옵션/수량 선택 후 주문 화면',variable=self.buy,command=self.buy_changed)
        purchase.grid(row=0,column=0,sticky='w',pady=(0,12))
        self.editors.append((purchase,'normal'))
        ttk.Label(right,text='Npay 포인트 사용').grid(row=1,column=0,sticky='w')
        points=ttk.Frame(right)
        points.grid(row=2,column=0,sticky='w',pady=5)
        for value,label in [('none','사용 안함'),('amount','금액 지정'),('all','전액사용')]:
            r=ttk.Radiobutton(points,text=label,value=value,variable=self.vars['points_mode'])
            r.pack(side='left',padx=(0,8))
            self.editors.append((r,'normal'))
        self.entry(right,'points_amount',3)
        ttk.Label(right,text='금액 지정 시 사용할 포인트 (원)',foreground='#6b7785').grid(row=4,column=0,sticky='w')
        ttk.Label(right,text='다른 결제수단').grid(row=5,column=0,sticky='w',pady=(12,4))
        card=ttk.Combobox(right,textvariable=self.vars['card'],values=CARDS,state='readonly')
        card.grid(row=6,column=0,sticky='ew',ipady=4)
        self.editors.append((card,'readonly'))
        ttk.Label(right,text='배송 방법: 택배').grid(row=7,column=0,sticky='w',pady=10)
        ttk.Label(right,text='배송비 포함 최대 결제금액 (원)').grid(row=8,column=0,sticky='w')
        self.entry(right,'limit',9)
        pay=ttk.Checkbutton(right,text='한도 내 결제하기 버튼까지 자동 클릭',variable=self.auto_pay)
        pay.grid(row=10,column=0,sticky='w',pady=8)
        self.editors.append((pay,'normal'))
        ttk.Label(right,text='결제 비밀번호').grid(row=11,column=0,sticky='w')
        secret=ttk.Entry(right,textvariable=self.password,show='●')
        secret.grid(row=12,column=0,sticky='ew',ipady=4,pady=4)
        self.editors.append((secret,'normal'))
        ttk.Label(right,text='이번 실행에만 사용 · 파일 저장 안함',foreground='#6b7785').grid(row=13,column=0,sticky='w')
        timing=ttk.LabelFrame(outer,text='시작 시간',padding=12)
        timing.pack(fill='x',pady=12)
        ttk.Label(timing,text='티켓팅 시작 시간 (한국시간)').grid(row=0,column=0,sticky='w',padx=(0,12))
        start=ttk.Entry(timing,textvariable=self.vars['start_time'],width=23)
        start.grid(row=0,column=1,sticky='w')
        self.editors.append((start,'normal'))
        ttk.Label(timing,text='YYYY-MM-DD HH:MM:SS').grid(row=0,column=2,padx=10,sticky='w')
        ttk.Label(timing,text='새로고침 간격').grid(row=1,column=0,sticky='w',pady=(8,0))
        interval=ttk.Entry(timing,textvariable=self.vars['interval'],width=8)
        interval.grid(row=1,column=1,sticky='w',pady=(8,0))
        self.editors.append((interval,'normal'))
        ttk.Label(timing,text='초 · 1초 이상 / 서버 지연에 따라 달라집니다.').grid(row=1,column=2,sticky='w',padx=10,pady=(8,0))
        modes=ttk.Frame(outer)
        modes.pack(fill='x')
        for value,label in [('demo','연습 · 실제 결제 없음'),('live','실제 상품')]:
            r=ttk.Radiobutton(modes,text=label,value=value,variable=self.vars['mode'])
            r.pack(side='left',padx=(0,16))
            self.editors.append((r,'normal'))
        ttk.Label(modes,text='최대 감시').pack(side='left',padx=(10,4))
        duration=ttk.Entry(modes,textvariable=self.vars['duration'],width=5)
        duration.pack(side='left')
        self.editors.append((duration,'normal'))
        ttk.Label(modes,text='분').pack(side='left',padx=4)
        ttk.Button(modes,text='로그인 브라우저 열기',command=self.login).pack(side='right')
        self.phase_var=tk.StringVar(value='OFF')
        self.message=tk.StringVar(value='설정 후 오른쪽 위 ON을 켜세요. 처음에는 연습 모드로 확인하세요.')
        self.amount=tk.StringVar(value='결제금액: 확인 전')
        status=ttk.Frame(outer)
        status.pack(fill='x',pady=(12,4))
        ttk.Label(status,textvariable=self.phase_var,style='State.TLabel').pack(side='left')
        ttk.Label(status,textvariable=self.amount).pack(side='right')
        ttk.Label(outer,textvariable=self.message,wraplength=950).pack(anchor='w')
        self.logs=tk.Text(outer,height=4,state='disabled',wrap='word',background='#eef2f3',relief='flat',font=('맑은 고딕',9))
        self.logs.pack(fill='both',expand=True,pady=(8,0))
        self.render_options()

    def entry(self,parent,key,row):
        entry=ttk.Entry(parent,textvariable=self.vars[key])
        entry.grid(row=row,column=0,sticky='ew',ipady=4,pady=4)
        self.editors.append((entry,'normal'))
        return entry

    def search_changed(self,*_):
        self.selection.set('')
        self.displayed_labels=None
        if hasattr(self,'option_frame'):
            self.render_options()

    def buy_changed(self):
        if not self.buy.get():
            self.auto_pay.set(False)

    def render_options(self):
        query=normalized(self.vars['option'].get())
        labels=[label for label in self.option_labels if query and query in normalized(label)]
        if self.displayed_labels==labels:
            return
        self.displayed_labels=labels
        for child in self.option_frame.winfo_children():
            child.destroy()
        if len(labels)==1 and not self.selection.get():
            self.selection.set(labels[0])
            self.option_selected()
        for index,label in enumerate(labels,1):
            tk.Checkbutton(self.option_frame,text=f'{index}. {label}',variable=self.selection,
                           onvalue=label,offvalue='',command=self.option_selected,wraplength=440,
                           justify='left',anchor='w',background='#f6f8f9',font=('맑은 고딕',10)).pack(anchor='w',pady=3)
        self.option_note.configure(text='일치하는 옵션이 없습니다.' if not labels else f'검색 결과 {len(labels)}개')
        self.selected_text.set('선택: '+(self.selection.get() or '—'))

    def option_selected(self):
        self.selected_text.set('선택: '+(self.selection.get() or '—'))
        if self.worker and self.worker.is_alive():
            self.worker.choose_option(self.selection.get())
            try:
                save(self.config_path,self.settings())
            except (ValueError,OSError):
                self.log('옵션 선택은 현재 실행에 적용했지만 파일 저장에는 실패했습니다.')

    def emit(self,kind,value):
        self.events.put((kind,value))

    def log(self,message):
        self.logs.configure(state='normal')
        self.logs.insert('end',f'{now_kst():%H:%M:%S} {message}\n')
        if int(self.logs.index('end-1c').split('.')[0])>500:
            self.logs.delete('1.0','51.0')
        self.logs.see('end')
        self.logs.configure(state='disabled')

    def settings(self):
        values={key:var.get() for key,var in self.vars.items()}
        values.update(action='prepare' if self.buy.get() else 'notify',auto_pay=self.auto_pay.get(),
                      selected_option=self.selection.get(),opening=self.vars['start_time'].get())
        return Settings.from_dict(values)

    def launch(self,auto_start):
        if self.worker and self.worker.is_alive():
            if auto_start:
                self.worker.arm()
            return
        try:
            settings=self.settings()
            secret=self.password.get()
            if secret and (len(secret)!=6 or not secret.isascii() or not secret.isdigit()):
                raise ValueError('Npay 결제 비밀번호는 6자리 숫자로 입력하거나 비워 두세요.')
            save(self.config_path,settings)
            self.worker=Session(settings,self.directory,self.emit,password=secret,auto_start=auto_start)
            self.password.set('')
            self.stock.set('확인 중')
            self.amount.set('결제금액: 확인 전')
            for editor,_ in self.editors:
                editor.configure(state='disabled')
            self.phase_var.set('브라우저 시작')
            self.message.set('실행 설정을 고정했습니다. ON이면 예약 시각에 자동 진행합니다.')
            self.worker.start()
        except (ValueError,KeyError,TypeError,OSError) as exc:
            self.on.set(False)
            messagebox.showerror('설정 확인',str(exc))

    def login(self):
        self.launch(False)

    def toggle(self):
        if self.on.get():
            self.launch(True)
        else:
            self.stop()

    def turn_on(self):
        self.on.set(True)
        self.launch(True)

    def pause(self):
        if self.worker and self.worker.is_alive() and not self.worker.review_event.is_set():
            if self.worker.pause_event.is_set():
                self.worker.pause_event.clear()
                self.phase_var.set('재개')
            else:
                self.worker.pause_event.set()
                self.phase_var.set('일시정지')

    def stop(self):
        self.on.set(False)
        if self.worker and self.worker.is_alive():
            self.worker.stop_event.set()
            self.message.set('OFF 요청 · 진행 중인 작업 종료 후 브라우저를 닫습니다.')

    def poll(self):
        self.clock.set(now_kst().strftime('%Y-%m-%d %H:%M:%S KST'))
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='hotkey':
                    action={1:self.turn_on,2:self.pause,3:self.stop}.get(value)
                    if action:
                        action()
                elif kind=='log':
                    self.log(value)
                elif kind=='state':
                    self.phase=value[0]
                    self.phase_var.set(PHASES.get(value[0],value[0]))
                    self.message.set(value[1])
                    self.log(value[1])
                    if value[0]=='review':
                        self.root.bell()
                elif kind=='stock':
                    self.stock.set(value)
                elif kind=='options':
                    self.option_labels=value
                    self.render_options()
                elif kind=='selected':
                    self.selection.set(value)
                    self.selected_text.set('선택: '+value)
                elif kind=='amount':
                    self.amount.set('결제금액: '+(f'{value:,}원' if value is not None else '직접 확인'))
                elif kind=='done':
                    self.on.set(False)
                    for editor,state in self.editors:
                        editor.configure(state=state)
                    if self.phase!='error':
                        self.phase_var.set('OFF')
                        self.message.set('세션 종료 · 새 실행 전에 주문 내역을 확인하세요.')
        except Empty:
            pass
        self.root.after(100,self.poll)

    def close(self):
        self.stop()
        self.wait_close()

    def wait_close(self):
        if self.worker and self.worker.is_alive():
            self.root.after(100,self.wait_close)
            return
        self.password.set('')
        if self.hotkeys:
            self.hotkeys.stop()
        self.root.destroy()


def main():
    root=tk.Tk()
    App(root)
    root.mainloop()


if __name__=='__main__':
    main()
