import os
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
import tkinter.font as tkfont
import unittest
from unittest.mock import patch,Mock
from smartstore.app import App,BG


@unittest.skipUnless(os.getenv('DISPLAY') or os.name=='nt','GUI display required')
class UiTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.root=tk.Tk()
        with patch('smartstore.app.data_dir',return_value=Path(self.temp.name)):
            self.app=App(self.root)
        self.root.update()
        self.app.fit_window()
        self.root.update()

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_black_background_and_larger_log_font(self):
        self.assertEqual(self.root.cget('background'),BG)
        expected=-round(self.root.winfo_fpixels('1p')*9*1.25)
        self.assertEqual(int(self.root.tk.splitlist(self.app.logs.cget('font'))[1]),expected)
        baseline=tkfont.Font(family=self.app.font_family,size=-round(self.root.winfo_fpixels('1p')*9))
        enlarged=tkfont.Font(font=self.app.logs.cget('font'))
        self.assertGreater(enlarged.metrics('linespace'),baseline.metrics('linespace'))

    def test_right_half_window_and_scroll(self):
        self.assertLessEqual(self.root.winfo_width(),self.root.winfo_screenwidth()//2+2)
        self.assertGreaterEqual(self.root.winfo_x(),self.root.winfo_screenwidth()//2-2)
        self.app.canvas.yview_moveto(1)
        self.root.update()
        self.assertAlmostEqual(self.app.canvas.yview()[1],1,places=2)
        self.app.arrange_columns(1200)
        self.assertEqual(self.app.left.grid_info()['columnspan'],1)
        self.app.arrange_columns(640)
        self.assertEqual(self.app.left.grid_info()['columnspan'],2)

    def test_two_detected_groups_and_no_options_toggle(self):
        self.app.receive_groups([dict(index=0,name='색상',labels=['화이트','블랙']),
                                 dict(index=1,name='사이즈',labels=['L','XL'])])
        self.assertEqual(len(self.app.group_vars),2)
        self.app.group_vars[0][0].set('블랙')
        self.app.group_vars[1][0].set('XL')
        self.assertEqual([spec.selected for spec in self.app.specs()],['블랙','XL'])
        self.app.no_options.set(True)
        self.app.no_options_changed()
        self.assertTrue(all(str(row[0].cget('state'))=='disabled' for row in self.app.group_rows))
        self.assertEqual(self.app.settings().groups,())

    def test_editing_query_does_not_apply_partial_input(self):
        worker=Mock()
        worker.is_alive.return_value=True
        self.app.worker=worker
        self.app.group_vars[0][0].set('블')
        worker.configure_options.assert_not_called()
        self.app.send_groups()
        worker.configure_options.assert_called_once()
        self.app.worker=None
