"""UI-only regression tests, no Firebase, Railway or LINE calls."""
import sys
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'website'))
from platform_shanlin_unified_ui import (unified_index, unified_script, unified_css, unified_frame)

class TestUnifiedShanlin(unittest.TestCase):
    def test_same_admin_pane_not_two_external_sites(self):
        html=unified_index()
        self.assertIn('id="shanlinUnifiedBookings"',html)
        self.assertIn('id="shanlinBookingFrame"',html)
        self.assertNotIn('href="https://shanlin-bot-production.up.railway.app/admin.html"',html)
        self.assertNotIn('href="http://127.0.0.1:5500/admin.html"',html)
        for pane in ('overview','clinic','staff','catalog','appointments'):
            self.assertIn(f'data-admin-pane="{pane}"',html)

    def test_single_session_and_local_embedding(self):
        js=unified_script()
        self.assertIn("clinic==='shanlin' && pane==='appointments'",js)
        self.assertIn("/api/pilot/admin/shanlin/booking-frame",js)
        self.assertIn("$('shanlinUnifiedBookings').hidden=!embedded",js)
        self.assertIn("await request('/admin/state')",js)
        self.assertIn("await request('/admin/session')",js)

    def test_color_system_kept(self):
        css=unified_css()
        self.assertIn('--main:#8BA8BA',css)
        self.assertIn('#365c73',css)
        self.assertIn('#shanlinBookingFrame',css)

    def test_frame_retains_safety_and_shows_correct_status(self):
        html=unified_frame()
        self.assertIn('unified-embedded',html)
        self.assertIn('const reason = typeof error.detail',html)
        self.assertIn("'時段名額已滿'",html)
        self.assertIn('取消後會釋出名額，並保留原預約紀錄。',html)
        self.assertIn('預約已取消，名額已釋出',html)
        self.assertNotIn('此操作無法復原',html)
        self.assertIn("new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Taipei'",html)
        self.assertIn('a.date<=sunday',html)
        self.assertIn("a.status!=='cancelled'",html)
        self.assertNotIn('開啟山林正式管理後台',html)

if __name__=='__main__':
    unittest.main()
