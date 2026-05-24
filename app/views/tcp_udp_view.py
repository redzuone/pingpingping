"""TCP/UDP tab view for client and server operations with multiple instances and detachable tabs."""

from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.services.tcp_service import TcpService
from app.services.udp_service import UdpService
from app.utils.app_settings import QuickSendPreset
from app.views.packet_log_widget import PacketLogWidget
from app.views.quick_send_presets import QuickSendPresetsWidget
from app.views.detachable_tab_widget import DetachableTabWidget


class _ConnectionInstanceWidget(QWidget):
    """A single TCP/UDP connection instance with config, send/receive, and packet log."""

    def __init__(
        self,
        title: str,
        protocol: str,  # 'tcp' or 'udp'
        mode: str,  # 'client' or 'server'
        tcp_service: TcpService,
        udp_service: UdpService,
        presets: list[QuickSendPreset] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._protocol = protocol
        self._mode = mode
        self._tcp_service = tcp_service
        self._udp_service = udp_service
        self._connection_id = f'{protocol}_{mode}_{id(self)}'
        self._is_connected = False
        self._presets = presets or []

        self._build_ui(title)

        # Connect service signals
        if protocol == 'tcp':
            self._tcp_service.client_connected.connect(self._on_client_connected)
            self._tcp_service.client_disconnected.connect(self._on_client_disconnected)
            self._tcp_service.client_data_received.connect(self._on_data_received)
            self._tcp_service.client_data_sent.connect(self._on_data_sent)
            self._tcp_service.client_error.connect(self._on_error)
            self._tcp_service.server_started.connect(self._on_server_started)
            self._tcp_service.server_stopped.connect(self._on_server_stopped)
            self._tcp_service.server_client_connected.connect(self._on_server_client_connected)
            self._tcp_service.server_client_disconnected.connect(self._on_server_client_disconnected)
            self._tcp_service.server_data_received.connect(self._on_server_data_received)
            self._tcp_service.server_data_sent.connect(self._on_server_data_sent)
            self._tcp_service.server_error.connect(self._on_error)
        else:
            self._udp_service.client_connected.connect(self._on_client_connected)
            self._udp_service.client_data_received.connect(self._on_udp_data_received)
            self._udp_service.client_data_sent.connect(self._on_data_sent)
            self._udp_service.client_error.connect(self._on_error)
            self._udp_service.server_started.connect(self._on_server_started)
            self._udp_service.server_stopped.connect(self._on_server_stopped)
            self._udp_service.server_data_received.connect(self._on_udp_server_data_received)
            self._udp_service.server_data_sent.connect(self._on_data_sent)
            self._udp_service.server_error.connect(self._on_error)

    def _build_ui(self, title: str) -> None:
        main_layout = QVBoxLayout(self)

        # Title and mode
        title_layout = QHBoxLayout()
        title_label = QLabel(f'<b>{title}</b>')
        title_label.setStyleSheet('font-size: 13px;')
        title_layout.addWidget(title_label)

        mode_label = QLabel(f'({self._protocol.upper()} {self._mode})')
        mode_label.setStyleSheet('color: #888;')
        title_layout.addWidget(mode_label)
        title_layout.addStretch()

        main_layout.addLayout(title_layout)

        # Connection config
        config_group = QGroupBox('Connection')
        config_layout = QHBoxLayout(config_group)

        self._host_input = QLineEdit()
        self._host_input.setPlaceholderText('Host/IP')

        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(8080)

        self._connect_btn = QPushButton('Connect' if self._mode == 'client' else 'Start')
        self._connect_btn.clicked.connect(self._on_connect)

        self._disconnect_btn = QPushButton('Disconnect' if self._mode == 'client' else 'Stop')
        self._disconnect_btn.setEnabled(False)
        self._disconnect_btn.clicked.connect(self._on_disconnect)

        self._connection_status = QLabel('● Disconnected')
        self._connection_status.setStyleSheet('color: #888;')

        config_layout.addWidget(QLabel('Host:'))
        config_layout.addWidget(self._host_input, 1)
        config_layout.addWidget(QLabel('Port:'))
        config_layout.addWidget(self._port_spin)
        config_layout.addWidget(self._connect_btn)
        config_layout.addWidget(self._disconnect_btn)
        config_layout.addWidget(self._connection_status)

        main_layout.addWidget(config_group)

        # Quick send presets
        self._quick_send = QuickSendPresetsWidget(
            presets=self._presets,
            on_send=self._send_data,
        )
        main_layout.addWidget(self._quick_send)

        # Send area
        send_group = QGroupBox('Send Data')
        send_layout = QVBoxLayout(send_group)

        send_controls = QHBoxLayout()
        self._send_input = QPlainTextEdit()
        self._send_input.setMaximumHeight(60)
        self._send_input.setPlaceholderText('Type message or hex here...')

        self._send_mode_combo = QComboBox()
        self._send_mode_combo.addItems(['Text (UTF-8)', 'Hex'])
        send_controls.addWidget(QLabel('Mode:'))
        send_controls.addWidget(self._send_mode_combo)

        self._send_btn = QPushButton('Send')
        self._send_btn.setEnabled(False)
        self._send_btn.clicked.connect(self._on_send)
        send_controls.addWidget(self._send_btn)

        self._clear_send_btn = QPushButton('Clear')
        self._clear_send_btn.clicked.connect(lambda: self._send_input.clear())
        send_controls.addWidget(self._clear_send_btn)

        send_layout.addWidget(self._send_input)
        send_layout.addLayout(send_controls)

        main_layout.addWidget(send_group)

        # Packet log
        log_group = QGroupBox('Packet Log')
        log_layout = QVBoxLayout(log_group)
        self._packet_log = PacketLogWidget()
        log_layout.addWidget(self._packet_log)

        self._clear_log_btn = QPushButton('Clear Log')
        self._clear_log_btn.clicked.connect(self._packet_log.clear_log)
        log_layout.addWidget(self._clear_log_btn)

        main_layout.addWidget(log_group, 1)

    def get_presets(self) -> list[QuickSendPreset]:
        return self._quick_send.get_presets()

    def set_presets(self, presets: list[QuickSendPreset]) -> None:
        self._quick_send.set_presets(presets)

    def cleanup(self) -> None:
        """Disconnect/stop when closing."""
        if self._is_connected:
            self._on_disconnect()

    def _send_data(self, data: bytes) -> None:
        """Send data via the appropriate service."""
        if not self._is_connected:
            return

        host = self._host_input.text().strip()
        port = self._port_spin.value()

        if self._protocol == 'tcp':
            if self._mode == 'client':
                self._tcp_service.send_client_data(self._connection_id, data)
            else:
                # For server, send to all connected clients
                self._tcp_service.send_server_data_all(data)
        else:
            if self._mode == 'client':
                self._udp_service.send_client_data(self._connection_id, host, port, data)
            else:
                self._udp_service.send_server_data((host, port), data)

    def _update_connection_state(self) -> None:
        self._connect_btn.setEnabled(not self._is_connected)
        self._disconnect_btn.setEnabled(self._is_connected)
        self._send_btn.setEnabled(self._is_connected)
        if self._is_connected:
            self._connection_status.setText('● Connected')
            self._connection_status.setStyleSheet('color: #4CAF50;')
        else:
            self._connection_status.setText('● Disconnected')
            self._connection_status.setStyleSheet('color: #888;')

    @Slot()
    def _on_connect(self) -> None:
        host = self._host_input.text().strip()
        port = self._port_spin.value()
        if not host:
            return

        if self._protocol == 'tcp':
            if self._mode == 'client':
                self._tcp_service.connect_client(self._connection_id, host, port)
            else:
                self._tcp_service.start_server(self._connection_id, host, port)
        else:
            if self._mode == 'client':
                self._udp_service.create_client(self._connection_id)
                self._is_connected = True
                self._update_connection_state()
            else:
                self._udp_service.start_server(self._connection_id, host, port)

    @Slot()
    def _on_disconnect(self) -> None:
        if self._protocol == 'tcp':
            if self._mode == 'client':
                self._tcp_service.disconnect_client(self._connection_id)
            else:
                self._tcp_service.stop_server()
        else:
            if self._mode == 'client':
                self._udp_service.disconnect_client(self._connection_id)
            else:
                self._udp_service.stop_server()
        self._is_connected = False
        self._update_connection_state()

    @Slot()
    def _on_send(self) -> None:
        """Send the contents of the send input."""
        text = self._send_input.toPlainText().strip()
        if not text:
            return

        mode = self._send_mode_combo.currentText()
        try:
            if 'Hex' in mode:
                hex_str = text.replace(' ', '').replace('\n', '').replace('\r', '')
                data = bytes.fromhex(hex_str)
            else:
                data = text.encode('utf-8')
            self._send_data(data)
        except ValueError as e:
            self._packet_log.add_packet('ERROR', str(e).encode(), source='Input')

    # TCP Client slots
    @Slot(str)
    def _on_client_connected(self, connection_id: str) -> None:
        if connection_id == self._connection_id:
            self._is_connected = True
            self._update_connection_state()
            self._packet_log.add_packet('INFO', b'Connected')

    @Slot(str)
    def _on_client_disconnected(self, connection_id: str) -> None:
        if connection_id == self._connection_id:
            self._is_connected = False
            self._update_connection_state()
            self._packet_log.add_packet('INFO', b'Disconnected')

    @Slot(str, bytes, str)
    def _on_data_received(self, connection_id: str, data: bytes, timestamp: str) -> None:
        if connection_id == self._connection_id:
            self._packet_log.add_packet('RX', data, source='Remote', timestamp=timestamp)

    @Slot(str, bytes, str)
    def _on_data_sent(self, connection_id: str, data: bytes, timestamp: str) -> None:
        if connection_id == self._connection_id:
            self._packet_log.add_packet('TX', data, source='Local', timestamp=timestamp)

    @Slot(str, str)
    def _on_error(self, connection_id: str, error_message: str) -> None:
        if connection_id == self._connection_id:
            self._packet_log.add_packet('ERROR', error_message.encode(), source='System')

    # Server slots (TCP/UDP)
    @Slot(str, int)
    def _on_server_started(self, host: str, port: int) -> None:
        if self._mode == 'server':
            self._is_connected = True
            self._update_connection_state()
            self._packet_log.add_packet('INFO', f'Server listening on {host}:{port}'.encode(), source='System')

    def _on_server_stopped(self) -> None:
        if self._mode == 'server':
            self._is_connected = False
            self._update_connection_state()
            self._packet_log.add_packet('INFO', b'Server stopped', source='System')

    # TCP Server slots
    @Slot(str, str)
    def _on_server_client_connected(self, server_id: str, client_addr: str) -> None:
        if server_id == self._connection_id:
            self._packet_log.add_packet('INFO', f'Client connected: {client_addr}'.encode(), source='System')

    @Slot(str, str)
    def _on_server_client_disconnected(self, server_id: str, client_addr: str) -> None:
        if server_id == self._connection_id:
            self._packet_log.add_packet('INFO', f'Client disconnected: {client_addr}'.encode(), source='System')

    @Slot(str, str, bytes, str)
    def _on_server_data_received(
        self, server_id: str, client_addr: str, data: bytes, timestamp: str
    ) -> None:
        if server_id == self._connection_id:
            self._packet_log.add_packet('RX', data, source=client_addr, timestamp=timestamp)

    @Slot(str, str, bytes, str)
    def _on_server_data_sent(
        self, server_id: str, client_addr: str, data: bytes, timestamp: str
    ) -> None:
        if server_id == self._connection_id:
            self._packet_log.add_packet('TX', data, source=client_addr, timestamp=timestamp)

    # UDP Client slots
    @Slot(str, bytes, str, int)
    def _on_udp_data_received(
        self, connection_id: str, data: bytes, from_host: str, from_port: int
    ) -> None:
        if connection_id == self._connection_id:
            addr = f'{from_host}:{from_port}'
            self._packet_log.add_packet('RX', data, source=addr)

    # UDP Server slots
    @Slot(str, str, bytes, int, int)
    def _on_udp_server_data_received(
        self, server_id: str, from_host: str, data: bytes, from_port: int, length: int
    ) -> None:
        if server_id == self._connection_id:
            addr = f'{from_host}:{from_port}'
            self._packet_log.add_packet('RX', data, source=addr)


class TcpUdpView(QWidget):
    """Combined TCP/UDP tab with multiple instances, detachable tabs, and quick-send presets."""

    def __init__(
        self,
        tcp_service: TcpService,
        udp_service: UdpService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tcp_service = tcp_service
        self._udp_service = udp_service
        self._instances: list[_ConnectionInstanceWidget] = []
        self._global_presets: list[QuickSendPreset] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Top controls
        controls_layout = QHBoxLayout()

        self._protocol_combo = QComboBox()
        self._protocol_combo.addItems(['TCP', 'UDP'])

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(['Client', 'Server'])

        self._add_instance_btn = QPushButton('+ New Instance')
        self._add_instance_btn.clicked.connect(self._on_add_instance)

        controls_layout.addWidget(QLabel('<b>Protocol:</b>'))
        controls_layout.addWidget(self._protocol_combo)
        controls_layout.addSpacing(10)
        controls_layout.addWidget(QLabel('<b>Mode:</b>'))
        controls_layout.addWidget(self._mode_combo)
        controls_layout.addSpacing(10)
        controls_layout.addWidget(self._add_instance_btn)
        controls_layout.addStretch()

        layout.addLayout(controls_layout)

        # Detachable tab widget for instances
        self._instance_tabs = DetachableTabWidget()
        self._instance_tabs.tabCloseRequested.connect(self._on_close_tab)

        layout.addWidget(self._instance_tabs, 1)

    def set_presets(self, presets: list[QuickSendPreset]) -> None:
        """Set global quick-send presets for all instances."""
        self._global_presets = presets
        for inst in self._instances:
            inst.set_presets(presets)

    def get_all_presets(self) -> list[QuickSendPreset]:
        """Get all presets (uses first instance's presets as canonical)."""
        if self._instances:
            return self._instances[0].get_presets()
        return self._global_presets

    @Slot()
    def _on_add_instance(self) -> None:
        protocol = self._protocol_combo.currentText().lower()
        mode = self._mode_combo.currentText().lower()
        instance_num = len(self._instances) + 1
        title = f'{protocol.upper()} {mode.title()} #{instance_num}'

        instance = _ConnectionInstanceWidget(
            title=title,
            protocol=protocol,
            mode=mode,
            tcp_service=self._tcp_service,
            udp_service=self._udp_service,
            presets=list(self._global_presets),
        )

        self._instances.append(instance)
        self._instance_tabs.addTab(instance, title)
        self._instance_tabs.setCurrentWidget(instance)

    def _find_instance_by_widget(self, widget: QWidget) -> _ConnectionInstanceWidget | None:
        """Find a stored instance by its widget reference."""
        for inst in self._instances:
            if inst is widget:
                return inst
        return None

    @Slot(int)
    def _on_close_tab(self, index: int) -> None:
        widget = self._instance_tabs.widget(index)
        if isinstance(widget, _ConnectionInstanceWidget):
            widget.cleanup()
            if widget in self._instances:
                self._instances.remove(widget)

        self._instance_tabs.removeTab(index)
        widget.deleteLater()

    def cleanup_all(self) -> None:
        """Cleanup all instances and close detached windows."""
        # First close all detached windows (which re-attaches tabs)
        self._instance_tabs.closeAllDetachedWindows()

        # Then cleanup each instance
        for inst in self._instances:
            inst.cleanup()

        # Clear instances and tabs
        while self._instance_tabs.count():
            w = self._instance_tabs.widget(0)
            self._instance_tabs.removeTab(0)
            if isinstance(w, _ConnectionInstanceWidget):
                if w in self._instances:
                    self._instances.remove(w)
            if w is not None:
                w.deleteLater()
