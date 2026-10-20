"""Place only this application's windows; leave existing Chrome windows alone."""
from dataclasses import dataclass
import ctypes
import sys


@dataclass(frozen=True)
class Bounds:
    left: int
    top: int
    width: int
    height: int

    def geometry(self):
        return f'{self.width}x{self.height}{self.left:+}{self.top:+}'


def halves(width=1920,height=1080,left=0,top=0):
    half=width//2
    return Bounds(left,top,half,height),Bounds(left+half,top,width-half,height)


def desktop_halves(root=None):
    if sys.platform=='win32':
        from ctypes import wintypes
        rect=wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x30,0,ctypes.byref(rect),0):
            return halves(rect.right-rect.left,rect.bottom-rect.top,rect.left,rect.top)
    if root is not None:
        return halves(root.winfo_screenwidth(),root.winfo_screenheight())
    return halves()


def place_chrome(context,page,bounds):
    session=context.new_cdp_session(page)
    try:
        window=session.send('Browser.getWindowForTarget')
        session.send('Browser.setWindowBounds',{'windowId':window['windowId'],
            'bounds':{'windowState':'normal'}})
        session.send('Browser.setWindowBounds',{'windowId':window['windowId'],'bounds':
            {'left':bounds.left,'top':bounds.top,'width':bounds.width,'height':bounds.height}})
    finally:
        session.detach()
