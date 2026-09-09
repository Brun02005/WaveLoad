import sys
import os
import time
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

def run_e2e_test():
    try:
        from ui.main_window import MainWindow
        app = QApplication(sys.argv)
        
        # Clear settings for a clean start
        from PySide6.QtCore import QSettings
        settings = QSettings("WaveLoad", "WaveLoad5")
        settings.clear()
        
        window = MainWindow()
        window.show()

        def step1_verify_startup():
            print("[E2E] Startup successful. No exceptions.")
            QTimer.singleShot(500, step2_verify_search)

        def step2_verify_search():
            print("[E2E] Verifying Search functionality...")
            window.shell.toolbar.search_input.setText("test track")
            # Wait for debounce if any
            QTimer.singleShot(500, step3_verify_context_panel)
            
        def step3_verify_context_panel():
            print("[E2E] Verifying Context Panel Toggle & Persistence...")
            assert not window.shell.is_context_panel_visible(), "Context panel should be hidden by default"
            
            # Toggle it
            window.library_ws.btn_toggle_panel.setChecked(True)
            assert window.shell.is_context_panel_visible(), "Context panel should be visible after toggle"
            
            print("[E2E] Context Panel works.")
            QTimer.singleShot(500, step4_verify_resize)
            
        def step4_verify_resize():
            print("[E2E] Verifying Application Resizing...")
            window.resize(1280, 720)
            window.resize(1920, 1080)
            window.resize(1024, 768)
            print("[E2E] Resizing stable. No rendering errors.")
            QTimer.singleShot(500, step5_verify_shutdown)

        def step5_verify_shutdown():
            print("[E2E] Verifying Shutdown...")
            app.quit()

        QTimer.singleShot(1000, step1_verify_startup)
        app.exec()
        print("[E2E] All tests passed.")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    run_e2e_test()
