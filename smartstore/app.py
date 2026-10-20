"""Black, enlarged, scrollable control panel for a half-screen window."""
from queue import Queue,Empty
import os
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk,messagebox
from .rules import Settings,OptionSpec,now_kst,CARDS
from .storage import data_dir,load,save
from .session import Session
from .hotkeys import WindowsHotkeys
from .browser import normalized
from .time_fields import split_time,join_time
from .window_layout import desktop_halves,Bounds

BG='#080a0d'
CARD='#14181d'
INPUT='#20262e'
FG='#f4f7fb'
MUTED='#a8b3c0'
GREEN='#43dd92'
PHASES={'idle':'OFF','opening':'크롬 시작','ready':'준비','scheduled':'예약 대기',
        'watching':'ON · 감시 중','choice':'옵션 입력/선택 필요','paused':'일시정지',
        'review':'직접 확인 필요','error':'오류','finished':'OFF'}


class App:
    def __init__(self,root):
        self.root,self.worker,self.hotkeys=root,None,None
        self.events=Queue()
        self.directory=data_dir()
        self.config_path=self.directory/'settings.json'
        self.phase='idle'
        self.closing=False
        self.editors=[]
        self.vars={}
        self.group_vars=[]
        self.group_rows=[]
        self.group_metadata=[]
        self.cached_specs=()
        self.detected_count=None
        self.rebuilding=False
        settings,warning=load(self.config_path)
        self.cached_specs=settings.option_groups or (OptionSpec(settings.option,settings.selected_option),)
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
        self.fit_after=root.after(100,self.fit_window)
        self.poll_after=root.after(100,self.poll)

    def font(self,size=10,bold=False):
        pixels=max(1,round(self.root.winfo_fpixels('1p')*size*1.25))
        return (self.font_family,-pixels,'bold' if bold else 'normal')

    def fit_window(self):
        _,area=desktop_halves(self.root)
        border=max(0,self.root.winfo_rootx()-self.root.winfo_x())
        top=max(0,self.root.winfo_rooty()-self.root.winfo_y())
        self.root.geometry(Bounds(area.left,area.top,max(360,area.width-2*border),
                                  max(520,area.height-top-border)).geometry())

    def build(self,settings):
        root=self.root
        available={name.casefold() for name in tkfont.families(root)}
        self.font_family=next((name for name in ('맑은 고딕','Malgun Gothic','Noto Sans CJK KR','Arial','Helvetica')
                               if name.casefold() in available),tkfont.nametofont('TkDefaultFont').actual('family'))
        root.title('스마트스토어 자동 클릭 · BLACK')
        _,area=desktop_halves(root)
        root.geometry(area.geometry())
        root.minsize(360,520)
        root.configure(background=BG)
        root.option_add('*Font',self.font())
        root.option_add('*TCombobox*Listbox.font',self.font())
        root.option_add('*TCombobox*Listbox.background',INPUT)
        root.option_add('*TCombobox*Listbox.foreground',FG)
        style=ttk.Style()
        style.theme_use('clam')
        for name in ('TFrame','TLabelframe'):
            style.configure(name,background=CARD)
        style.configure('TLabel',background=CARD,foreground=FG,font=self.font())
        style.configure('TLabelframe.Label',background=CARD,foreground=GREEN,font=self.font(11,True))
        for name in ('TCheckbutton','TRadiobutton'):
            style.configure(name,background=CARD,foreground=FG,font=self.font())
            style.map(name,background=[('active',INPUT)],foreground=[('disabled','#66717f')])
        for name in ('TEntry','TCombobox','TSpinbox'):
            style.configure(name,fieldbackground=INPUT,background=INPUT,foreground=FG,
                            insertcolor=FG,font=self.font(),bordercolor='#353d48',arrowsize=18)
            style.map(name,fieldbackground=[('disabled','#111419'),('readonly',INPUT)],
                      foreground=[('disabled','#66717f'),('readonly',FG)])
        style.configure('TButton',padding=(10,8),font=self.font(),background=INPUT,foreground=FG)
        style.map('TButton',background=[('active','#304036')])
        style.configure('Vertical.TScrollbar',background=INPUT,troughcolor=BG,arrowcolor=FG)
        header=ttk.Frame(root,padding=(16,12))
        header.pack(fill='x')
        ttk.Label(header,text='스마트스토어 자동 클릭',font=self.font(21,True),foreground=GREEN).pack(anchor='w')
        line=ttk.Frame(header)
        line.pack(fill='x',pady=(8,0))
        self.clock=tk.StringVar()
        ttk.Label(line,textvariable=self.clock,foreground=MUTED,font=self.font(9)).pack(side='left')
        self.on=tk.BooleanVar(value=False)
        ttk.Checkbutton(line,text='프로그램 ON / OFF',variable=self.on,command=self.toggle).pack(side='right')
        holder=ttk.Frame(root)
        holder.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(holder,background=BG,highlightthickness=0)
        scrollbar=ttk.Scrollbar(holder,orient='vertical',command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right',fill='y')
        self.canvas.pack(side='left',fill='both',expand=True)
        self.body=ttk.Frame(self.canvas,padding=12)
        self.body_window=self.canvas.create_window((0,0),window=self.body,anchor='nw')
        self.body.bind('<Configure>',lambda event:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',self.resize_body)
        root.bind_all('<MouseWheel>',self.scroll)
        root.bind_all('<Button-4>',lambda event:self.canvas.yview_scroll(-3,'units'))
        root.bind_all('<Button-5>',lambda event:self.canvas.yview_scroll(3,'units'))
        values=settings.to_dict()
        for key in ('url','quantity','limit','interval','duration','points_amount','card','points_mode'):
            self.vars[key]=tk.StringVar(value=str(values[key]))
        self.vars['mode']=tk.StringVar(value='demo')
        self.time_vars={key:tk.StringVar(value=value) for key,value in
                        split_time(settings.start_at.strftime('%Y-%m-%d %H:%M:%S')).items()}
        self.buy=tk.BooleanVar(value=settings.action=='prepare')
        self.auto_pay=tk.BooleanVar(value=settings.auto_pay)
        self.no_options=tk.BooleanVar(value=settings.no_options)
        self.password=tk.StringVar()
        self.columns=ttk.Frame(self.body)
        self.columns.pack(fill='x')
        self.columns.columnconfigure(0,weight=1)
        self.columns.columnconfigure(1,weight=1)
        self.left=ttk.LabelFrame(self.columns,text='상품 · 제품 수량',padding=14)
        self.right=ttk.LabelFrame(self.columns,text='구매 · 결제',padding=14)
        self.left.columnconfigure(0,weight=1)
        self.right.columnconfigure(0,weight=1)
        ttk.Label(self.left,text='판매 링크').pack(anchor='w')
        self.entry(self.left,'url')
        self.stock=tk.StringVar(value='확인 전')
        self.purchase_status=tk.StringVar(value='구매 버튼: 확인 전')
        ttk.Label(self.left,textvariable=self.stock,foreground=GREEN,font=self.font(13,True)).pack(anchor='w',pady=8)
        ttk.Label(self.left,textvariable=self.purchase_status,foreground=MUTED).pack(anchor='w')
        self.option_count=tk.StringVar(value='옵션 개수: 브라우저에서 확인 전')
        ttk.Label(self.left,textvariable=self.option_count).pack(anchor='w',pady=(14,4))
        ttk.Checkbutton(self.left,text='제품 옵션 없음',variable=self.no_options,
                        command=self.no_options_changed).pack(anchor='w',pady=4)
        self.option_frame=ttk.Frame(self.left)
        self.option_frame.pack(fill='x',pady=6)
        self.rebuild_groups(settings.option_groups or (OptionSpec(settings.option,settings.selected_option),))
        qty=ttk.Frame(self.left)
        qty.pack(fill='x',pady=(12,0))
        ttk.Label(qty,text='제품 수량').pack(side='left')
        entry=ttk.Spinbox(qty,from_=1,to=99,textvariable=self.vars['quantity'],width=5)
        entry.pack(side='left',padx=12)
        self.editors.append((entry,'normal'))
        ttk.Label(qty,text='개').pack(side='left')
        for parent,text,var,command in [(self.right,'구매하기',self.buy,self.buy_changed),
                                        (self.right,'한도 내 결제하기까지 자동 클릭',self.auto_pay,None)]:
            widget=ttk.Checkbutton(parent,text=text,variable=var,command=command)
            widget.pack(anchor='w',pady=(0,8))
            self.editors.append((widget,'normal'))
        ttk.Label(self.right,text='Npay 포인트 사용').pack(anchor='w',pady=(8,0))
        points=ttk.Frame(self.right)
        points.pack(fill='x',pady=4)
        for value,label in [('none','사용 안함'),('amount','금액 지정'),('all','전액사용')]:
            r=ttk.Radiobutton(points,text=label,value=value,variable=self.vars['points_mode'])
            r.pack(side='left',padx=(0,8))
            self.editors.append((r,'normal'))
        self.entry(self.right,'points_amount')
        ttk.Label(self.right,text='금액 지정 시 사용할 포인트 (원)',foreground=MUTED,font=self.font(9)).pack(anchor='w')
        ttk.Label(self.right,text='다른 결제수단').pack(anchor='w',pady=(12,4))
        card=ttk.Combobox(self.right,textvariable=self.vars['card'],values=CARDS,state='readonly')
        card.pack(fill='x',ipady=4)
        self.editors.append((card,'readonly'))
        ttk.Label(self.right,text='배송 방법: 택배').pack(anchor='w',pady=10)
        ttk.Label(self.right,text='배송비 포함 최대 결제금액 (원)').pack(anchor='w')
        self.entry(self.right,'limit')
        ttk.Label(self.right,text='결제 비밀번호').pack(anchor='w',pady=(8,0))
        secret=ttk.Entry(self.right,textvariable=self.password,show='●')
        secret.pack(fill='x',ipady=4,pady=4)
        self.editors.append((secret,'normal'))
        ttk.Label(self.right,text='이번 실행에만 사용 · 파일 저장 안함',foreground=MUTED,font=self.font(9)).pack(anchor='w')
        timing=ttk.LabelFrame(self.body,text='티켓팅 시작 시간 · 한국시간',padding=14)
        timing.pack(fill='x',pady=12)
        for parts in [('year','month','day'),('ampm','hour','minute','second')]:
            line=ttk.Frame(timing)
            line.pack(fill='x',pady=4)
            labels={'year':'년','month':'월','day':'일','ampm':'','hour':'시','minute':'분','second':'초'}
            ranges={'month':range(1,13),'day':range(1,32),'hour':range(1,13),'minute':range(60),'second':range(60)}
            for key in parts:
                if key=='year':
                    entry=ttk.Entry(line,textvariable=self.time_vars[key],width=5)
                    state='normal'
                else:
                    options=('AM','PM') if key=='ampm' else tuple(f'{v:02}' for v in ranges[key])
                    entry=ttk.Combobox(line,textvariable=self.time_vars[key],values=options,
                                       width=4 if key=='ampm' else 3,state='readonly')
                    state='readonly'
                entry.pack(side='left',padx=(0,4),ipady=4)
                self.editors.append((entry,state))
                if labels[key]:
                    ttk.Label(line,text=labels[key]).pack(side='left',padx=(0,8))
        refresh=ttk.Frame(timing)
        refresh.pack(fill='x',pady=(10,0))
        ttk.Label(refresh,text='새로고침').pack(side='left')
        interval=ttk.Spinbox(refresh,from_=.1,to=5,increment=.1,textvariable=self.vars['interval'],width=5)
        interval.pack(side='left',padx=10)
        self.editors.append((interval,'normal'))
        ttk.Label(refresh,text='초 (0.1~5초)').pack(side='left')
        ttk.Label(timing,text='응답 완료 후 간격입니다. 서버 응답 시간은 별도입니다.',
                  foreground=MUTED,font=self.font(9),wraplength=500).pack(anchor='w',pady=(6,0))
        modes=ttk.LabelFrame(self.body,text='실행',padding=14)
        modes.pack(fill='x')
        for value,label in [('demo','연습 · 실제 결제 없음'),('live','실제 상품 · Google Chrome')]:
            radio=ttk.Radiobutton(modes,text=label,value=value,variable=self.vars['mode'])
            radio.pack(anchor='w',pady=3)
            self.editors.append((radio,'normal'))
        line=ttk.Frame(modes)
        line.pack(fill='x',pady=(8,0))
        ttk.Label(line,text='최대 감시').pack(side='left')
        duration=ttk.Entry(line,textvariable=self.vars['duration'],width=4)
        duration.pack(side='left',padx=8)
        self.editors.append((duration,'normal'))
        ttk.Label(line,text='분').pack(side='left')
        ttk.Button(modes,text='크롬 열기 · 로그인 확인',command=self.login).pack(fill='x',pady=(10,0))
        footer=ttk.Frame(root,padding=(16,10))
        footer.pack(fill='x')
        self.phase_var=tk.StringVar(value='OFF')
        self.message=tk.StringVar(value='설정 후 ON · 크롬 왼쪽 / 프로그램 오른쪽')
        self.amount=tk.StringVar(value='결제금액: 확인 전')
        ttk.Label(footer,textvariable=self.phase_var,foreground=GREEN,font=self.font(13,True)).pack(anchor='w')
        ttk.Label(footer,textvariable=self.amount,font=self.font(9)).pack(anchor='w',pady=3)
        self.message_label=ttk.Label(footer,textvariable=self.message,foreground=MUTED,wraplength=550,font=self.font(9))
        self.message_label.pack(anchor='w')
        self.logs=tk.Text(footer,height=3,state='disabled',wrap='word',background=BG,foreground=FG,
                          insertbackground=FG,relief='flat',font=self.font(9),padx=8,pady=6)
        self.logs.pack(fill='x',pady=(6,0))
        self.arrange_columns(area.width)

    def resize_body(self,event):
        self.canvas.itemconfigure(self.body_window,width=event.width)
        self.arrange_columns(event.width)
        if hasattr(self,'message_label'):
            self.message_label.configure(wraplength=max(280,event.width-40))

    def arrange_columns(self,width):
        if not hasattr(self,'left'):
            return
        if width>=1000:
            self.left.grid(row=0,column=0,columnspan=1,sticky='nsew',padx=(0,6))
            self.right.grid(row=0,column=1,columnspan=1,sticky='nsew',padx=(6,0))
        else:
            self.left.grid(row=0,column=0,columnspan=2,sticky='ew')
            self.right.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(12,0))

    def scroll(self,event):
        # Leave open combobox dropdowns and text log scrolling to their widgets.
        if event.widget==self.logs or str(event.widget).find('popdown')>=0:
            return
        self.canvas.yview_scroll(-int(event.delta/120) if abs(event.delta)>=120 else (-1 if event.delta>0 else 1),'units')

    def entry(self,parent,key):
        entry=ttk.Entry(parent,textvariable=self.vars[key])
        entry.pack(fill='x',ipady=4,pady=4)
        self.editors.append((entry,'normal'))
        return entry

    def rebuild_groups(self,specs):
        self.rebuilding=True
        for child in self.option_frame.winfo_children():
            child.destroy()
        self.group_vars=[]
        self.group_rows=[]
        for index,spec in enumerate(specs):
            frame=ttk.LabelFrame(self.option_frame,text=f'옵션 {index+1}',padding=8)
            frame.pack(fill='x',pady=4)
            query=tk.StringVar(value=spec.query)
            selected=tk.StringVar(value=spec.selected)
            entry=ttk.Entry(frame,textvariable=query)
            entry.pack(fill='x',ipady=4,pady=3)
            entry.bind('<Return>',lambda event:self.send_groups())
            ttk.Button(frame,text='옵션 적용',command=self.send_groups).pack(anchor='e',pady=3)
            choices=ttk.Frame(frame)
            choices.pack(fill='x')
            note=ttk.Label(frame,text='검색 문구 입력 (예: 블랙 / XL)',foreground=MUTED,font=self.font(9))
            note.pack(anchor='w',pady=3)
            self.group_vars.append((query,selected))
            self.group_rows.append((entry,choices,note))
            query.trace_add('write',lambda *_,i=index:self.query_changed(i))
        self.rebuilding=False
        self.render_groups()

    def render_groups(self):
        for index,(query,selected) in enumerate(self.group_vars):
            entry,frame,note=self.group_rows[index]
            entry.configure(state='disabled' if self.no_options.get() else 'normal')
            meta=self.group_metadata[index] if index<len(self.group_metadata) else {}
            labels=[label for label in meta.get('labels',[]) if query.get().strip() and
                    normalized(query.get()) in normalized(label)]
            cache=(tuple(labels),self.no_options.get(),query.get())
            if getattr(frame,'render_cache',None)==cache:
                continue
            frame.render_cache=cache
            for child in frame.winfo_children():
                child.destroy()
            if len(labels)==1 and not selected.get() and not self.no_options.get():
                selected.set(labels[0])
            for label in labels:
                tk.Checkbutton(frame,text=label,variable=selected,onvalue=label,offvalue='',
                    command=self.send_groups,font=self.font(),background=CARD,foreground=FG,
                    activebackground=INPUT,activeforeground=FG,selectcolor=INPUT,
                    disabledforeground='#66717f',anchor='w',justify='left',wraplength=450,
                    state='disabled' if self.no_options.get() else 'normal').pack(anchor='w',fill='x')
            note.configure(text='옵션 없음: 선택란 비활성' if self.no_options.get() else
                           (f'검색 {len(labels)}개 / 선택: '+(selected.get() or '—')+' · 입력 후 적용/Enter' if meta else '검색 문구 입력 후 적용 (예: 블랙 / XL)'))

    def query_changed(self,index):
        if self.rebuilding:
            return
        self.group_vars[index][1].set('')
        self.render_groups()

    def no_options_changed(self):
        self.render_groups()
        self.send_groups()

    def specs(self):
        return tuple(OptionSpec(query.get().strip(),selected.get()) for query,selected in self.group_vars)

    def receive_groups(self,metadata):
        self.detected_count=len(metadata)
        self.option_count.set(f'옵션 개수: {len(metadata)}개 확인')
        before=self.specs()
        if before:
            self.cached_specs=before
        self.group_metadata=metadata
        if len(before)!=len(metadata):
            specs=tuple(self.cached_specs[i] if i<len(self.cached_specs) else OptionSpec() for i in range(len(metadata)))
            self.rebuild_groups(specs)
            self.send_groups()
        else:
            self.render_groups()

    def send_groups(self):
        if self.rebuilding:
            return
        if self.worker and self.worker.is_alive():
            self.worker.configure_options(self.specs(),self.no_options.get())
        try:
            save(self.config_path,self.settings())
        except (ValueError,OSError,KeyError):
            pass

    def buy_changed(self):
        if not self.buy.get():
            self.auto_pay.set(False)

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
        specs=self.specs()
        values.update(action='prepare' if self.buy.get() else 'notify',auto_pay=self.auto_pay.get(),
                      no_options=self.no_options.get(),option_groups=[dict(query=s.query,selected=s.selected) for s in specs],
                      option=specs[0].query if specs else '',selected_option=specs[0].selected if specs else '',
                      start_time=join_time({key:var.get() for key,var in self.time_vars.items()}))
        values['opening']=values['start_time']
        if values['points_mode']!='amount':
            values['points_amount']=0
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
                raise ValueError('Npay 결제 비밀번호는 6자리 숫자이거나 비워 두세요.')
            save(self.config_path,settings)
            self.worker=Session(settings,self.directory,self.emit,password=secret,auto_start=auto_start)
            self.password.set('')
            self.stock.set('확인 중')
            self.purchase_status.set('구매 버튼: 확인 중')
            self.amount.set('결제금액: 확인 전')
            for editor,_ in self.editors:
                editor.configure(state='disabled')
            self.phase_var.set('크롬 시작')
            self.worker.start()
        except (ValueError,KeyError,TypeError,OSError) as exc:
            self.on.set(False)
            messagebox.showerror('설정 확인',str(exc))

    def login(self):
        self.launch(False)

    def toggle(self):
        self.launch(True) if self.on.get() else self.stop()

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
            self.message.set('OFF 요청 · 진행 중인 작업 종료 후 크롬을 닫습니다.')

    def poll(self):
        if self.closing:
            return
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
                elif kind=='purchase_status':
                    self.purchase_status.set('구매 버튼: '+value)
                elif kind=='option_groups':
                    self.receive_groups(value)
                elif kind=='selected_groups':
                    for (_,selected),label in zip(self.group_vars,value):
                        selected.set(label)
                    self.render_groups()
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
        self.poll_after=self.root.after(100,self.poll)

    def close(self):
        self.closing=True
        self.stop()
        self.wait_close()

    def wait_close(self):
        if self.worker and self.worker.is_alive():
            self.root.after(100,self.wait_close)
            return
        self.password.set('')
        if self.hotkeys:
            self.hotkeys.stop()
        for timer in (self.fit_after,self.poll_after):
            try:
                self.root.after_cancel(timer)
            except tk.TclError:
                pass
        self.root.destroy()


def main():
    from .tk_runtime import configure_tk_paths
    configure_tk_paths()
    root=tk.Tk()
    App(root)
    root.mainloop()


if __name__=='__main__':
    main()
