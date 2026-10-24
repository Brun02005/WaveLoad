import logging
import os
import sys
import tempfile
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Windowed builds (console=False) leave sys.stdout/sys.stderr as None; anything
# that writes to them at import (logging StreamHandler, library warnings) then
# crashes the app before it can start. Give them a safe sink first of all.
# ---------------------------------------------------------------------------
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

logger = logging.getLogger("waveload.main")


def _setup_logging() -> None:
    """Writes to waveload_error.log next to the persistent data (project
    root in dev, next to the .exe when frozen — or wherever core.config
    fell back to if that location wasn't writable). If even resolving that
    location fails, falls back to the OS temp dir so a startup error is
    always logged and shown, never a bare unhandled traceback.
    """
    folders = None
    try:
        from core.config import BASE_DIR, OUTPUT_DIR  # noqa: PLC0415
        folders = (BASE_DIR, OUTPUT_DIR)
        log_file = BASE_DIR / "waveload_error.log"
    except Exception:  # noqa: BLE001
        log_file = Path(tempfile.gettempdir()) / "waveload_error.log"

    from logging.handlers import RotatingFileHandler  # noqa: PLC0415

    # INFO por defecto: en DEBUG el log llegó a 6 MB, dos tercios ruido.
    # WAVELOAD_DEBUG=1 lo vuelve a abrir para diagnosticar.
    level = logging.DEBUG if os.environ.get("WAVELOAD_DEBUG") else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            RotatingFileHandler(log_file, maxBytes=2 * 1024 * 1024,
                                backupCount=3, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Un crash nativo (Qt, DLLs de audio) no pasa por el except de main():
    # sin esto no deja ningún rastro.
    try:
        import faulthandler  # noqa: PLC0415
        crash_log = open(log_file.with_name("waveload_crash.log"), "a", encoding="utf-8")  # noqa: SIM115
        faulthandler.enable(file=crash_log)
    except Exception:  # noqa: BLE001
        pass

    # Record where everything lives. On someone else's PC these paths are the
    # first thing worth knowing when files "disappear".
    if folders:
        logger.info("Data folder: %s", folders[0])
        logger.info("Default download folder: %s", folders[1])


def main() -> None:
    # QApplication must exist before any Qt import side-effects.
    from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: PLC0415
    app = QApplication(sys.argv)

    try:
        _setup_logging()
        from core.config import expose_bundled_binaries  # noqa: PLC0415
        expose_bundled_binaries()
        from ui.main_window import MainWindow  # noqa: PLC0415
        window = MainWindow()
        window.show()
        logger.info("WaveLoad started successfully.")
        sys.exit(app.exec())

    except Exception:  # noqa: BLE001
        tb = traceback.format_exc()
        logger.critical("Fatal startup error:\n%s", tb)

        # Show the full traceback in a dialog so the user sees it even when
        # launched by double-click (no console visible).
        msg = QMessageBox()
        msg.setWindowTitle("WaveLoad — Error de inicio")
        msg.setIcon(QMessageBox.Critical)
        msg.setText("La aplicación no pudo iniciarse.\nRevisa waveload_error.log para más detalles.")
        msg.setDetailedText(tb)
        msg.exec()
        sys.exit(1)


if __name__ == "__main__":
    main()
