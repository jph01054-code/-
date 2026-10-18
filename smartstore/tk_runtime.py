"""Locate the Tcl/Tk data shipped with the active Windows Python runtime.

Only process-local defaults are set. Existing explicit overrides are preserved.
The compiled extension supplies the required versions; no downloads or version
guesses are used.
"""
import os
from pathlib import Path
import sys


def configure_tk_paths():
    if sys.platform != 'win32':
        return False
    import _tkinter
    base = Path(sys.base_prefix)
    tcl = f'tcl{_tkinter.TCL_VERSION}'
    tk = f'tk{_tkinter.TK_VERSION}'
    for parent in (base / 'tcl', base / 'lib', base):
        tcl_dir, tk_dir = parent / tcl, parent / tk
        if (tcl_dir / 'init.tcl').is_file() and (tk_dir / 'tk.tcl').is_file():
            os.environ.setdefault('TCL_LIBRARY', str(tcl_dir))
            os.environ.setdefault('TK_LIBRARY', str(tk_dir))
            return True
    return False
