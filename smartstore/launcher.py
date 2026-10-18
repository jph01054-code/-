"""Keep Windows startup failures visible, including missing Tcl/Tk."""
import ctypes
import os
from pathlib import Path
import sys
import traceback


def log_path():
    return Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'SmartStoreAssistantV2' / 'startup-error.log'


def write_error():
    path = log_path()
    details = (f'Python: {sys.version}\nExecutable: {sys.executable}\n'
               f'Folder: {Path.cwd()}\n\n{traceback.format_exc()}')
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(details, encoding='utf-8')
        return path
    except OSError:
        return None


def show_error(path):
    message = ('프로그램 시작에 실패했습니다.\n\n'
               'install.bat을 실행한 뒤 start.bat을 다시 실행하세요.\n'
               'Python 설치에는 Tcl/Tk가 포함되어 있어야 합니다.\n\n')
    message += f'오류 기록: {path}' if path else '오류 기록을 저장하지 못했습니다. 검은 창의 오류를 확인하세요.'
    if os.name == 'nt':
        try:
            ctypes.windll.user32.MessageBoxW(None, message, '스마트스토어 실행 오류', 0x10)
            return
        except (AttributeError, OSError):
            pass
    print(message, file=sys.stderr)


def start_application(check=False):
    import tkinter as tk
    from .app import App
    root = tk.Tk()
    root.withdraw()
    try:
        app = App(root)
        if check:
            app.close()
            print('GUI construction: OK')
        else:
            root.deiconify()
            root.mainloop()
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass


def main(check=False):
    try:
        start_application(check=check)
        return 0
    except Exception:
        path = write_error()
        traceback.print_exc()
        show_error(path)
        return 1


if __name__ == '__main__':
    sys.exit(main(check='--check' in sys.argv[1:]))
