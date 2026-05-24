"""TCP client and server service."""

from __future__ import annotations

import socket
import struct
import threading
import time
from datetime import UTC, datetime
from typing import Any

from PySide6.QtCore import QObject, Signal


class TcpService(QObject):
    """TCP client and server service with multiple connection support."""

    # Client signals
    client_connected = Signal(str)  # connection_id
    client_disconnected = Signal(str)  # connection_id
    client_data_received = Signal(str, bytes, str)  # connection_id, data, timestamp
    client_data_sent = Signal(str, bytes, str)  # connection_id, data, timestamp
    client_error = Signal(str, str)  # connection_id, error_message

    # Server signals
    server_started = Signal(str, int)  # bind_host, port
    server_stopped = Signal()
    server_client_connected = Signal(str, str)  # server_id, client_addr
    server_client_disconnected = Signal(str, str)  # server_id, client_addr
    server_data_received = Signal(str, str, bytes, str)  # server_id, client_addr, data, timestamp
    server_data_sent = Signal(str, str, bytes, str)  # server_id, client_addr, data, timestamp
    server_error = Signal(str, str)  # server_id, error_message

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._clients: dict[str, socket.socket] = {}
        self._client_threads: dict[str, threading.Thread] = {}
        self._client_running: dict[str, bool] = {}

        self._server_socket: socket.socket | None = None
        self._server_running = False
        self._server_thread: threading.Thread | None = None
        self._server_connections: dict[str, socket.socket] = {}
        self._server_conn_threads: dict[str, threading.Thread] = {}

    def connect_client(self, connection_id: str, host: str, port: int) -> None:
        """Connect a TCP client."""
        if connection_id in self._clients:
            return

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((host, port))
            sock.settimeout(None)
            self._clients[connection_id] = sock
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
        """Disconnect a TCP client."""
        self._client_running[connection_id] = False
        sock = self._clients.pop(connection_id, None)
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        self.client_disconnected.emit(connection_id)

    def send_client_data(self, connection_id: str, data: bytes) -> None:
        """Send data through a TCP client connection."""
        sock = self._clients.get(connection_id)
        if sock is None:
            self.client_error.emit(connection_id, 'Not connected')
            return

        try:
            sock.sendall(data)
            timestamp = datetime.now(UTC).isoformat()
            self.client_data_sent.emit(connection_id, data, timestamp)
        except Exception as e:
            self.client_error.emit(connection_id, str(e))

    def _client_receive_loop(self, connection_id: str, sock: socket.socket) -> None:
        """Receive loop for a client connection."""
        while self._client_running.get(connection_id, False):
            try:
                data = sock.recv(65536)
                if not data:
                    break
                timestamp = datetime.now(UTC).isoformat()
                self.client_data_received.emit(connection_id, data, timestamp)
            except (socket.timeout, BlockingIOError):
                continue
            except Exception as e:
                if self._client_running.get(connection_id, False):
                    self.client_error.emit(connection_id, str(e))
                break
        self.disconnect_client(connection_id)

    def start_server(self, server_id: str, host: str, port: int) -> None:
        """Start a TCP server."""
        if self._server_running:
            return

        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind((host, port))
            self._server_socket.listen(5)
            self._server_socket.settimeout(1)
            self._server_running = True

            self._server_thread = threading.Thread(
                target=self._server_accept_loop,
                args=(server_id,),
                daemon=True,
            )
            self._server_thread.start()

            self.server_started.emit(host, port)
        except Exception as e:
            self.server_error.emit(server_id, str(e))

    def stop_server(self) -> None:
        """Stop the TCP server."""
        self._server_running = False
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except Exception:
                pass
            self._server_socket = None

        # Close all server connections
        for client_addr in list(self._server_connections.keys()):
            self._close_server_connection(client_addr)

        self.server_stopped.emit()

    def send_server_data(self, client_addr: str, data: bytes) -> None:
        """Send data to a connected server client."""
        sock = self._server_connections.get(client_addr)
        if sock is None:
            return

        try:
            sock.sendall(data)
            timestamp = datetime.now(UTC).isoformat()
            self.server_data_sent.emit('server', client_addr, data, timestamp)
        except Exception:
            self._close_server_connection(client_addr)

    def send_server_data_all(self, data: bytes) -> None:
        """Send data to all connected server clients."""
        for client_addr in list(self._server_connections.keys()):
            self.send_server_data(client_addr, data)

    def _server_accept_loop(self, server_id: str) -> None:
        """Accept loop for the server."""
        while self._server_running:
            try:
                if self._server_socket is None:
                    break
                client_sock, addr = self._server_socket.accept()
                client_addr = f'{addr[0]}:{addr[1]}'
                self._server_connections[client_addr] = client_sock

                thread = threading.Thread(
                    target=self._server_client_receive_loop,
                    args=(server_id, client_addr, client_sock),
                    daemon=True,
                )
                self._server_conn_threads[client_addr] = thread
                thread.start()

                self.server_client_connected.emit(server_id, client_addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self._server_running:
                    self.server_error.emit(server_id, str(e))
                break

    def _server_client_receive_loop(
        self, server_id: str, client_addr: str, sock: socket.socket
    ) -> None:
        """Receive loop for a server client connection."""
        try:
            while self._server_running:
                data = sock.recv(65536)
                if not data:
                    break
                timestamp = datetime.now(UTC).isoformat()
                self.server_data_received.emit(server_id, client_addr, data, timestamp)
        except Exception:
            pass
        finally:
            self._close_server_connection(client_addr)
            self.server_client_disconnected.emit(server_id, client_addr)

    def _close_server_connection(self, client_addr: str) -> None:
        """Close a server client connection."""
        sock = self._server_connections.pop(client_addr, None)
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        self._server_conn_threads.pop(client_addr, None)

    def cleanup(self) -> None:
        """Cleanup all connections and server."""
        self.stop_server()
        for connection_id in list(self._clients.keys()):
            self.disconnect_client(connection_id)
