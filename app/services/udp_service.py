"""UDP client and server service."""

from __future__ import annotations

import socket
import threading
from datetime import UTC, datetime

from PySide6.QtCore import QObject, Signal


class UdpService(QObject):
    """UDP client and server service with multiple connection support."""

    # Client signals
    client_connected = Signal(str)  # connection_id
    client_data_received = Signal(str, bytes, str, int)  # connection_id, data, from_host, from_port
    client_data_sent = Signal(str, bytes, str)  # connection_id, data, timestamp
    client_error = Signal(str, str)  # connection_id, error_message

    # Server signals
    server_started = Signal(str, int)  # bind_host, port
    server_stopped = Signal()
    server_data_received = Signal(str, str, bytes, int, int)  # server_id, from_host, data, from_port, length
    server_data_sent = Signal(str, str, bytes, str)  # server_id, to_addr, data, timestamp
    server_error = Signal(str, str)  # server_id, error_message

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._client_sockets: dict[str, socket.socket] = {}
        self._client_running: dict[str, bool] = {}
        self._client_threads: dict[str, threading.Thread] = {}

        self._server_socket: socket.socket | None = None
        self._server_running = False
        self._server_thread: threading.Thread | None = None

    def create_client(self, connection_id: str, bind_port: int = 0) -> None:
        """Create a UDP client socket."""
        if connection_id in self._client_sockets:
            return

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1)
            if bind_port > 0:
                sock.bind(('0.0.0.0', bind_port))

            self._client_sockets[connection_id] = sock
            self._client_running[connection_id] = True

            thread = threading.Thread(
                target=self._client_receive_loop,
                args=(connection_id, sock),
                daemon=True,
            )
            self._client_threads[connection_id] = thread
            thread.start()

            self.client_connected.emit(connection_id)
        except Exception as e:
            self.client_error.emit(connection_id, str(e))

    def disconnect_client(self, connection_id: str) -> None:
        """Disconnect/release a UDP client."""
        self._client_running[connection_id] = False
        sock = self._client_sockets.pop(connection_id, None)
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        self.client_connected.emit(connection_id)  # Signal to update UI (intentionally emits connected to indicate creation)
        # No explicit disconnection signal since UDP is connectionless

    def send_client_data(self, connection_id: str, host: str, port: int, data: bytes) -> None:
        """Send data through a UDP client."""
        sock = self._client_sockets.get(connection_id)
        if sock is None:
            self.client_error.emit(connection_id, 'Client not created')
            return

        try:
            sock.sendto(data, (host, port))
            timestamp = datetime.now(UTC).isoformat()
            self.client_data_sent.emit(connection_id, data, timestamp)
        except Exception as e:
            self.client_error.emit(connection_id, str(e))

    def _client_receive_loop(self, connection_id: str, sock: socket.socket) -> None:
        """Receive loop for a UDP client."""
        while self._client_running.get(connection_id, False):
            try:
                data, addr = sock.recvfrom(65536)
                from_host, from_port = addr
                self.client_data_received.emit(
                    connection_id, data, from_host, from_port
                )
            except socket.timeout:
                continue
            except Exception as e:
                if self._client_running.get(connection_id, False):
                    self.client_error.emit(connection_id, str(e))
                break

    def start_server(self, server_id: str, host: str, port: int) -> None:
        """Start a UDP server."""
        if self._server_running:
            return

        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind((host, port))
            self._server_socket.settimeout(1)
            self._server_running = True

            self._server_thread = threading.Thread(
                target=self._server_receive_loop,
                args=(server_id,),
                daemon=True,
            )
            self._server_thread.start()

            self.server_started.emit(host, port)
        except Exception as e:
            self.server_error.emit(server_id, str(e))

    def stop_server(self) -> None:
        """Stop the UDP server."""
        self._server_running = False
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except Exception:
                pass
            self._server_socket = None
        self.server_stopped.emit()

    def send_server_data(self, target_addr: tuple[str, int], data: bytes) -> None:
        """Send data to a specific address from the server."""
        if self._server_socket is None:
            return

        try:
            self._server_socket.sendto(data, target_addr)
            timestamp = datetime.now(UTC).isoformat()
            addr_str = f'{target_addr[0]}:{target_addr[1]}'
            self.server_data_sent.emit('server', addr_str, data, timestamp)
        except Exception as e:
            self.server_error.emit('server', str(e))

    def _server_receive_loop(self, server_id: str) -> None:
        """Receive loop for the UDP server."""
        while self._server_running:
            try:
                if self._server_socket is None:
                    break
                data, addr = self._server_socket.recvfrom(65536)
                from_host, from_port = addr
                self.server_data_received.emit(
                    server_id, from_host, data, from_port, len(data)
                )
            except socket.timeout:
                continue
            except Exception as e:
                if self._server_running:
                    self.server_error.emit(server_id, str(e))
                break

    def cleanup(self) -> None:
        """Cleanup all connections and server."""
        self.stop_server()
        for connection_id in list(self._client_sockets.keys()):
            self.disconnect_client(connection_id)
