import ctypes
from ctypes import wintypes
from threading import Thread, Event


class WindowsHotkeys(Thread):
    def __init__(self, emit):
        super().__init__(daemon=True)
        self.emit = emit
        self.stopping = Event()
        self.thread_id = None

    def run(self):
        user = ctypes.windll.user32
        user.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user.GetMessageW.restype = wintypes.BOOL
        self.thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        registered = []
        try:
            for ident, key in [(1, 0x77), (2, 0x78), (3, 0x79)]:
                if user.RegisterHotKey(None, ident, 0x4000, key):
                    registered.append(ident)
                else:
                    self.emit('log', f'F{key - 0x6F} 핫키 등록 실패: 화면 버튼을 사용하세요.')
            msg = wintypes.MSG()
            while not self.stopping.is_set():
                if user.GetMessageW(ctypes.byref(msg), None, 0, 0) <= 0:
                    break
                if msg.message == 0x0312:
                    self.emit('hotkey', msg.wParam)
        finally:
            for ident in registered:
                user.UnregisterHotKey(None, ident)

    def stop(self):
        self.stopping.set()
        if self.thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
