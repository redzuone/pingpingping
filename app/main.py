import multiprocessing as mp
import os
import sys

import qt_themes  # type: ignore[import-untyped]
from PySide6.QtWidgets import QApplication

from app.constants import APP_DISPLAY_NAME
from app.views.main_window import MainWindow


def main() -> None:
    # Fix Uvicorn logging when frozen without a console
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w')

    app = QApplication(sys.argv)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    qt_themes.set_theme('one_dark_two')

    view = MainWindow()
    view.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    mp.freeze_support()
    main()
