"""Main application window with tabbed interface."""

from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QMainWindow,
    QTabWidget,
    QMessageBox,
    QMenuBar,
    QMenu,
    QStatusBar,
    QLabel,
)

from app.views.pinger_view import PingerView
from app.views.tcp_udp_view import TcpUdpView
from app.services.pinger_service import PingerService
from app.services.tcp_service import TcpService
from app.services.udp_service import UdpService
from app.utils.app_settings import (
    AppSettings,
    create_app_settings,
    load_settings,
    save_settings,
)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle('PingPingPing')
        self.resize(1200, 800)

        # Settings (QSettings-based, not JSON file)
        self._qs = create_app_settings()
        self._settings: AppSettings = load_settings(self._qs)

        # Services
        self._pinger_service = PingerService(self)
        self._tcp_service = TcpService(self)
        self._udp_service = UdpService(self)

        # Build UI
        self._build_menu_bar()
        self._build_central_widget()
        self._build_status_bar()

        # Load state from settings
        self._load_view_state()

    def _build_menu_bar(self) -> None:
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu('&File')
        file_menu.addAction('&Preferences', self._on_preferences)
        file_menu.addSeparator()
        file_menu.addAction('E&xit', self.close, 'Ctrl+Q')

        # Tools menu
        tools_menu = menubar.addMenu('&Tools')
        tools_menu.addAction('&Pinger', lambda: self._main_tabs.setCurrentIndex(0), 'Ctrl+1')
        tools_menu.addAction('&TCP/UDP', lambda: self._main_tabs.setCurrentIndex(1), 'Ctrl+2')

        # Help menu
        help_menu = menubar.addMenu('&Help')
        help_menu.addAction('&About', self._on_about)

    def _build_central_widget(self) -> None:
        self._main_tabs = QTabWidget()

        # Tab 1: Pinger
        self._pinger_view = PingerView(self._pinger_service)
        self._main_tabs.addTab(self._pinger_view, '🔍 Pinger')

        # Tab 2: TCP/UDP
        self._tcp_udp_view = TcpUdpView(
            tcp_service=self._tcp_service,
            udp_service=self._udp_service,
        )
        self._main_tabs.addTab(self._tcp_udp_view, '🌐 TCP/UDP')

        self.setCentralWidget(self._main_tabs)

    def _build_status_bar(self) -> None:
        status_bar = self.statusBar()
        self._status_label = QLabel('Ready')
        status_bar.addPermanentWidget(self._status_label)

    def _load_view_state(self) -> None:
        """Load state from settings into views."""
        self._pinger_view.load_settings(self._settings)
        self._tcp_udp_view.set_presets(self._settings.quick_send_presets)

    def closeEvent(self, event) -> None:  # noqa: N802
        """Save state on close."""
        # Stop all pinging first
        self._pinger_service.stop_all()
        # Cleanup TCP/UDP connections
        self._tcp_udp_view.cleanup_all()
        # Cleanup services
        self._tcp_service.cleanup()
        self._udp_service.cleanup()
        # Save state
        self._save_all_state()
        save_settings(self._qs, self._settings)
        event.accept()

    def _save_all_state(self) -> None:
        """Save all view state to settings."""
        self._pinger_view.save_settings(self._settings)
        self._settings.quick_send_presets = self._tcp_udp_view.get_all_presets()

    @Slot()
    def _on_preferences(self) -> None:
        QMessageBox.information(self, 'Preferences', 'Preferences dialog coming soon.')

    @Slot()
    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            'About PingPingPing',
            'PingPingPing v2\n\n'
            'A network monitoring and debugging tool.\n\n'
            'Features:\n'
            '- Multi-device pinger with status indicators\n'
            '- TCP client/server\n'
            '- UDP client/server\n'
            '- Packet logging with Wireshark-inspired view\n'
            '- Quick-send presets\n'
            '- Multiple connection instances',
        )
