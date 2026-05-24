"""QTabWidget that supports detaching tabs into separate windows."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class _DetachedWindow(QWidget):
    """A window that hosts a detached tab."""

    window_closed = Signal(str)  # tab_title

    def __init__(self, title: str, content: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle(title)
        self._content = content
        self._title = title

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Re-attach button bar
        header = QHBoxLayout()
        header.addStretch()
        self._reattach_btn = QPushButton('Re-attach Tab')
        self._reattach_btn.clicked.connect(self._on_reattach)
        header.addWidget(self._reattach_btn)

        title_label = QLabel(f'<b>{title}</b>')
        title_label.setStyleSheet('padding: 2px 8px;')
        header.addWidget(title_label)
        header.addStretch()

        layout.addLayout(header)
        layout.addWidget(content, 1)

        self.setMinimumSize(500, 400)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.window_closed.emit(self._title)
        event.accept()

    def _on_reattach(self) -> None:
        self.close()


class DetachableTabWidget(QTabWidget):
    """Tab widget where tabs can be detached into separate windows and re-attached."""

    tab_detached = Signal(str)  # tab_title
    tab_reattached = Signal(str)  # tab_title

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTabsClosable(True)
        self._detached_windows: dict[str, _DetachedWindow] = {}
        self._detached_contents: dict[str, QWidget] = {}

    def addTab(self, widget: QWidget, title: str) -> int:  # type: ignore[override]
        """Add a tab with a detach button."""
        idx = super().addTab(widget, title)

        # Add detach button to the tab
        detach_btn = QPushButton('⇱')
        detach_btn.setFixedSize(20, 20)
        detach_btn.setToolTip(f'Detach "{title}" to a separate window')
        detach_btn.clicked.connect(lambda checked, t=title: self.detach_tab(t))
        from PySide6.QtWidgets import QTabBar
        self.tabBar().setTabButton(idx, QTabBar.ButtonPosition.LeftSide, detach_btn)

        return idx

    def detach_tab(self, title: str) -> None:
        """Detach a tab into a separate window."""
        # Find the tab
        for idx in range(self.count()):
            if self.tabText(idx) == title:
                widget = self.widget(idx)
                if widget is None:
                    return

                # Remove from tab widget
                self.removeTab(idx)

                # Store content reference
                self._detached_contents[title] = widget

                # Create detached window
                detached = _DetachedWindow(title, widget)
                detached.window_closed.connect(self._on_detached_window_closed)
                self._detached_windows[title] = detached

                detached.show()
                self.tab_detached.emit(title)
                return

    def reattach_tab(self, title: str) -> None:
        """Re-attach a tab from a detached window back into the tab widget."""
        if title not in self._detached_windows:
            return

        window = self._detached_windows.pop(title, None)
        content = self._detached_contents.pop(title, None)

        if window is not None:
            content.setParent(None) if content else None
            window.close()
            window.deleteLater()

        if content is not None:
            self.addTab(content, title)
            self.setCurrentWidget(content)
            self.tab_reattached.emit(title)

    def _on_detached_window_closed(self, title: str) -> None:
        """Handle a detached window being closed (either by user or re-attach)."""
        content = self._detached_contents.pop(title, None)
        window = self._detached_windows.pop(title, None)

        if window is not None:
            window.deleteLater()

        if content is not None:
            content.setParent(None)
            self.addTab(content, title)
            self.setCurrentWidget(content)
            self.tab_reattached.emit(title)

    def closeAllDetachedWindows(self) -> None:  # noqa: N802
        """Close all detached windows and re-attach their content."""
        for title in list(self._detached_windows.keys()):
            self.reattach_tab(title)
