"""Pinger tab view for monitoring multiple devices."""

from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.pinger_service import PingerService, PingStatus
from app.utils.app_settings import PingDeviceConfig, AppSettings

# Column layout: Actions | Host/IP | Name | Status | Latency | Failures | Raw Output
_COL_ACTIONS = 0
_COL_HOST = 1
_COL_NAME = 2
_COL_STATUS = 3
_COL_LATENCY = 4
_COL_FAILURES = 5
_COL_RAW = 6
_COL_COUNT = 7


class _RecentIpsCompleter:
    """Simple in-memory recent IPs tracker (stored in settings)."""

    def __init__(self) -> None:
        self._recent: list[str] = []

    def load(self, devices: list[PingDeviceConfig]) -> None:
        self._recent = sorted({d.host for d in devices if d.host})

    def add(self, host: str) -> None:
        if host and host not in self._recent:
            self._recent.append(host)

    def get_all(self) -> list[str]:
        return list(self._recent)


class PingerView(QWidget):
    """Main pinger tab with device management and status display."""

    STATUS_COLORS = {
        PingStatus.OK: QColor('#4CAF50'),  # Green
        PingStatus.INTERMITTENT: QColor('#FFC107'),  # Yellow
        PingStatus.UNREACHABLE: QColor('#F44336'),  # Red
    }

    def __init__(
        self,
        pinger_service: PingerService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = pinger_service
        self._recent_ips = _RecentIpsCompleter()
        self._device_configs: dict[str, PingDeviceConfig] = {}

        # Connect service signals
        self._service.device_status_changed.connect(self._on_status_changed)
        self._service.device_latency.connect(self._on_latency)
        self._service.device_raw_output.connect(self._on_raw_output)
        self._service.device_error.connect(self._on_error)
        self._service.device_started.connect(self._on_device_started)
        self._service.device_stopped.connect(self._on_device_stopped)
        self._service.device_failure_log.connect(self._on_failure_log)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Control bar
        control_layout = QHBoxLayout()

        self._host_input = QLineEdit()
        self._host_input.setPlaceholderText('IP or hostname (e.g., 8.8.8.8)')
        self._host_input.returnPressed.connect(self._on_add_device)

        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(100, 60000)
        self._interval_spin.setValue(1000)
        self._interval_spin.setSuffix(' ms')
        self._interval_spin.setToolTip('Ping interval per device')

        self._add_btn = QPushButton('Add Device')
        self._add_btn.clicked.connect(self._on_add_device)

        self._start_all_btn = QPushButton('▶ Start All')
        self._start_all_btn.clicked.connect(self._on_start_all)

        self._stop_all_btn = QPushButton('■ Stop All')
        self._stop_all_btn.clicked.connect(self._on_stop_all)
        self._stop_all_btn.setEnabled(False)

        self._auto_start_cb = QCheckBox('Auto-start on launch')
        self._auto_start_cb.setChecked(True)

        control_layout.addWidget(QLabel('Host/IP:'))
        control_layout.addWidget(self._host_input, 1)
        control_layout.addWidget(QLabel('Interval:'))
        control_layout.addWidget(self._interval_spin)
        control_layout.addWidget(self._add_btn)
        control_layout.addSpacing(10)
        control_layout.addWidget(self._start_all_btn)
        control_layout.addWidget(self._stop_all_btn)
        control_layout.addWidget(self._auto_start_cb)

        layout.addLayout(control_layout)

        # Device table — Actions column first
        self._device_table = QTableWidget()
        self._device_table.setColumnCount(_COL_COUNT)
        self._device_table.setHorizontalHeaderLabels(
            ['Actions', 'Host/IP', 'Name', 'Status', 'Latency', 'Failures', 'Raw Output']
        )

        header = self._device_table.horizontalHeader()
        # Actions column: fixed width so buttons don't move around
        header.setSectionResizeMode(_COL_ACTIONS, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(_COL_ACTIONS, 110)
        header.setSectionResizeMode(_COL_HOST, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(_COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_LATENCY, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_FAILURES, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_RAW, QHeaderView.ResizeMode.Stretch)
        # Prevent column 0 from being moved
        self._device_table.setColumnWidth(_COL_ACTIONS, 110)

        self._device_table.setAlternatingRowColors(True)
        self._device_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._device_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        layout.addWidget(self._device_table, 2)

        # Raw output and failure log area
        bottom_split = QHBoxLayout()

        # Raw output
        output_layout = QVBoxLayout()
        output_layout.addWidget(QLabel('<b>Raw Ping Output</b>'))
        self._raw_output = QPlainTextEdit()
        self._raw_output.setReadOnly(True)
        self._raw_output.setMaximumBlockCount(500)
        self._raw_output.setFont(QFont('Consolas', 9))
        output_layout.addWidget(self._raw_output)
        bottom_split.addLayout(output_layout)

        # Failure log
        fail_layout = QVBoxLayout()
        fail_layout.addWidget(QLabel('<b>Failure Log</b>'))
        self._failure_log = QPlainTextEdit()
        self._failure_log.setReadOnly(True)
        self._failure_log.setMaximumBlockCount(500)
        self._failure_log.setFont(QFont('Consolas', 9))
        self._failure_log.setStyleSheet('color: #F44336;')
        fail_layout.addWidget(self._failure_log)
        bottom_split.addLayout(fail_layout)

        self._clear_log_btn = QPushButton('Clear Log')
        self._clear_log_btn.clicked.connect(self._on_clear_log)
        fail_layout.addWidget(self._clear_log_btn)

        layout.addLayout(bottom_split, 1)

    # ── Public API ──────────────────────────────────────────────

    def load_settings(self, settings: AppSettings) -> None:
        """Load saved devices and start pinging if auto-start enabled."""
        self._device_table.setRowCount(0)
        self._device_configs.clear()
        self._recent_ips.load(settings.pinger_devices)
        self._auto_start_cb.setChecked(settings.pinger_auto_start)

        for config in settings.pinger_devices:
            self._add_device_row(config)
            if config.enabled and settings.pinger_auto_start:
                self._start_ping(config.host)

    def save_settings(self, settings: AppSettings) -> None:
        """Save current devices to settings."""
        devices = list(self._device_configs.values())
        settings.pinger_devices = devices
        settings.pinger_auto_start = self._auto_start_cb.isChecked()

    # ── Device helpers ──────────────────────────────────────────

    def _add_device_row(self, config: PingDeviceConfig) -> None:
        """Add a device row to the table."""
        if config.host in self._device_configs:
            return

        self._device_configs[config.host] = config

        row = self._device_table.rowCount()
        self._device_table.insertRow(row)

        # Column 0: Actions (Start/Stop/Remove buttons)
        actions_widget = QWidget()
        actions_layout = QHBoxLayout(actions_widget)
        actions_layout.setContentsMargins(2, 0, 2, 0)

        start_btn = QPushButton('▶')
        start_btn.setFixedWidth(30)
        start_btn.setToolTip('Start pinging')
        start_btn.clicked.connect(lambda checked, h=config.host: self._start_ping(h))

        stop_btn = QPushButton('■')
        stop_btn.setFixedWidth(30)
        stop_btn.setToolTip('Stop pinging')
        stop_btn.setEnabled(False)
        stop_btn.clicked.connect(lambda checked, h=config.host: self._stop_ping(h))

        remove_btn = QPushButton('✕')
        remove_btn.setFixedWidth(25)
        remove_btn.setToolTip('Remove device')
        remove_btn.clicked.connect(lambda checked, h=config.host: self._remove_device(h))

        actions_layout.addWidget(start_btn)
        actions_layout.addWidget(stop_btn)
        actions_layout.addWidget(remove_btn)

        self._device_table.setCellWidget(row, _COL_ACTIONS, actions_widget)

        # Column 1: Host/IP
        self._device_table.setItem(row, _COL_HOST, QTableWidgetItem(config.host))

        # Column 2: Name
        name_item = QTableWidgetItem(config.friendly_name)
        self._device_table.setItem(row, _COL_NAME, name_item)

        # Column 3: Status (colored indicator with text)
        status_item = QTableWidgetItem(f'● {PingStatus.OK.value}')
        status_item.setForeground(self.STATUS_COLORS[PingStatus.OK])
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._device_table.setItem(row, _COL_STATUS, status_item)

        # Column 4: Latency
        latency_item = QTableWidgetItem('-')
        latency_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._device_table.setItem(row, _COL_LATENCY, latency_item)

        # Column 5: Failures count
        fail_item = QTableWidgetItem('0')
        fail_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._device_table.setItem(row, _COL_FAILURES, fail_item)

        # Column 6: Raw output placeholder
        self._device_table.setItem(row, _COL_RAW, QTableWidgetItem(''))

        self._device_table.setRowHeight(row, 30)

    def _start_ping(self, host: str) -> None:
        """Start pinging a device."""
        config = self._device_configs.get(host)
        if config is None:
            return
        self._service.start_ping(host, config.interval_ms)

    def _stop_ping(self, host: str) -> None:
        """Stop pinging a device. Blocks until the thread has fully stopped
        so that a subsequent _start_ping call works immediately."""
        self._service.stop_ping(host, wait=True)

    def _remove_device(self, host: str) -> None:
        """Remove a device from the list."""
        self._stop_ping(host)
        self._device_configs.pop(host, None)

        for row in range(self._device_table.rowCount()):
            item = self._device_table.item(row, _COL_HOST)
            if item and item.text() == host:
                self._device_table.removeRow(row)
                break

    def _toggle_actions(self, host: str, is_running: bool) -> None:
        """Toggle start/stop button states for a device row."""
        for row in range(self._device_table.rowCount()):
            item = self._device_table.item(row, _COL_HOST)
            if item and item.text() == host:
                widget = self._device_table.cellWidget(row, _COL_ACTIONS)
                if widget:
                    btns = widget.findChildren(QPushButton)
                    if len(btns) >= 2:
                        btns[0].setEnabled(not is_running)  # Start
                        btns[1].setEnabled(is_running)  # Stop
                break

    # ── Slots ───────────────────────────────────────────────────

    @Slot()
    def _on_add_device(self) -> None:
        host = self._host_input.text().strip()
        if not host:
            return

        config = PingDeviceConfig(
            host=host,
            friendly_name='',
            interval_ms=self._interval_spin.value(),
            enabled=self._auto_start_cb.isChecked(),
        )

        if host not in self._device_configs:
            self._add_device_row(config)
            self._recent_ips.add(host)
            if self._auto_start_cb.isChecked():
                self._start_ping(host)

        self._host_input.clear()

    @Slot()
    def _on_start_all(self) -> None:
        for host in self._device_configs:
            self._start_ping(host)
        self._start_all_btn.setEnabled(False)
        self._stop_all_btn.setEnabled(True)

    @Slot()
    def _on_stop_all(self) -> None:
        self._service.stop_all()
        self._start_all_btn.setEnabled(True)
        self._stop_all_btn.setEnabled(False)

    @Slot(str, PingStatus)
    def _on_status_changed(self, host: str, status: PingStatus) -> None:
        for row in range(self._device_table.rowCount()):
            item = self._device_table.item(row, _COL_HOST)
            if item and item.text() == host:
                status_item = self._device_table.item(row, _COL_STATUS)
                if status_item:
                    status_item.setForeground(self.STATUS_COLORS[status])
                    status_item.setText(f'● {status.value}')
                break

    @Slot(str, float)
    def _on_latency(self, host: str, latency: float) -> None:
        for row in range(self._device_table.rowCount()):
            item = self._device_table.item(row, _COL_HOST)
            if item and item.text() == host:
                lat_item = self._device_table.item(row, _COL_LATENCY)
                if latency > 0:
                    lat_item.setText(f'{latency:.1f} ms')
                    lat_item.setForeground(QColor('#000000'))
                else:
                    lat_item.setText('TIMEOUT')
                    lat_item.setForeground(QColor('#F44336'))
                break

    @Slot(str, str)
    def _on_raw_output(self, host: str, line: str) -> None:
        self._raw_output.appendPlainText(f'[{host}] {line}')

    @Slot(str, str)
    def _on_error(self, host: str, error_message: str) -> None:
        self._raw_output.appendPlainText(f'[ERROR] {host}: {error_message}')

    @Slot(str)
    def _on_device_started(self, host: str) -> None:
        self._toggle_actions(host, True)
        self._raw_output.appendPlainText(f'[INFO] Started pinging {host}')

        # If stop_all was previously run, re-enable the Stop All button
        if any(self._service.is_pinging(h) for h in self._device_configs):
            self._start_all_btn.setEnabled(False)
            self._stop_all_btn.setEnabled(True)

    @Slot(str)
    def _on_device_stopped(self, host: str) -> None:
        self._toggle_actions(host, False)
        self._raw_output.appendPlainText(f'[INFO] Stopped pinging {host}')
        # Reset stop all button if no devices running
        all_stopped = not any(
            self._service.is_pinging(h) for h in self._device_configs
        )
        if all_stopped:
            self._start_all_btn.setEnabled(True)
            self._stop_all_btn.setEnabled(False)

    @Slot(str, str)
    def _on_failure_log(self, host: str, timestamp: str) -> None:
        self._failure_log.appendPlainText(f'[{timestamp}] {host} - FAILED')
        # Update failure count
        for row in range(self._device_table.rowCount()):
            item = self._device_table.item(row, _COL_HOST)
            if item and item.text() == host:
                fail_item = self._device_table.item(row, _COL_FAILURES)
                if fail_item:
                    count = int(fail_item.text()) + 1
                    fail_item.setText(str(count))
                break

    @Slot()
    def _on_clear_log(self) -> None:
        self._failure_log.clear()
