"""Pinger service for continuously pinging multiple hosts using subprocess."""

from __future__ import annotations

import re
import subprocess
import time
from collections import deque
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

# Windows ping output patterns
_PING_STATS_RE = re.compile(
    r'Reply from .*? bytes=(\d+).*? time[<>=](\d+|\d+\.\d+)ms.*? TTL=(\d+)',
    re.IGNORECASE,
)
_PING_TIMEOUT_RE = re.compile(r'(Request timed out|Destination host unreachable)', re.IGNORECASE)
_PING_TTL_EXPIRED_RE = re.compile(r'TTL expired in transit', re.IGNORECASE)
_PING_GENERAL_FAILURE_RE = re.compile(r'(General failure|Ping transmit failed)', re.IGNORECASE)

# For newer PowerShell-based ping output
_PING_MS_RE = re.compile(r'time[=<]\s*(\d+)\s*ms', re.IGNORECASE)


class PingStatus(Enum):
    OK = 'ok'
    INTERMITTENT = 'intermittent'
    UNREACHABLE = 'unreachable'


class _PingWorker(QObject):
    """Worker that runs a continuous ping loop in a background thread."""

    result_ready = Signal(str, float)  # host, latency_ms (0.0 = failure)
    raw_output = Signal(str, str)  # host, raw_line
    finished = Signal(str)  # host
    error = Signal(str, str)  # host, error_message

    def __init__(
        self,
        host: str,
        interval_ms: int = 1000,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._host = host
        self._interval_s = max(0.5, interval_ms / 1000.0)
        self._running = False
        self._process: subprocess.Popen | None = None

    def run(self) -> None:
        """Start the continuous ping loop."""
        self._running = True
        ping_cmd = ['ping', '-t', self._host]

        try:
            self._process = subprocess.Popen(
                ping_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
                bufsize=1,
            )
        except FileNotFoundError:
            self.error.emit(self._host, 'ping.exe not found on system')
            self.finished.emit(self._host)
            return
        except Exception as e:
            self.error.emit(self._host, f'Failed to start ping: {e}')
            self.finished.emit(self._host)
            return

        try:
            while self._running and self._process.stdout:
                line = self._process.stdout.readline()
                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                # Parse the ping output
                latency = self._parse_ping_line(line)
                if latency is not None:
                    self.result_ready.emit(self._host, latency)
                self.raw_output.emit(self._host, line)
        finally:
            self._cleanup_process()

    def stop(self) -> None:
        """Signal the worker to stop."""
        self._running = False
        self._cleanup_process()

    def _cleanup_process(self) -> None:
        """Kill the subprocess if still running."""
        proc = self._process
        if proc is not None:
            self._process = None
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=3)
            except Exception:
                # Force kill if terminate didn't work
                try:
                    proc.kill()
                    proc.wait(timeout=2)
                except Exception:
                    pass

    def _parse_ping_line(self, line: str) -> float | None:
        """Parse a single ping output line.

        Returns:
            Latency in ms for successful replies.
            0.0 for failures (timeout, unreachable, etc.).
            None for unparseable lines (header, summary, empty, etc.).
        """
        # Check for successful reply
        match = _PING_STATS_RE.search(line)
        if match:
            try:
                latency = float(match.group(2))
                return latency
            except ValueError:
                return 0.0

        # Check for newer ping format (Windows 11)
        if 'time=' in line or 'time<' in line:
            ms_match = _PING_MS_RE.search(line)
            if ms_match:
                try:
                    return float(ms_match.group(1))
                except ValueError:
                    return 0.0

        # Check for failure patterns
        if _PING_TIMEOUT_RE.search(line):
            return 0.0
        if _PING_TTL_EXPIRED_RE.search(line):
            return 0.0
        if _PING_GENERAL_FAILURE_RE.search(line):
            return 0.0

        return None  # Unknown/unparseable line — ignore


class PingerService(QObject):
    """Manages multiple ping workers across threads."""

    device_status_changed = Signal(str, PingStatus)  # host, new_status
    device_latency = Signal(str, float)  # host, latency_ms
    device_raw_output = Signal(str, str)  # host, raw_line
    device_error = Signal(str, str)  # host, error
    device_started = Signal(str)  # host
    device_stopped = Signal(str)  # host
    device_failure_log = Signal(str, str)  # host, timestamp_when_failed

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._workers: dict[str, _PingWorker] = {}
        self._threads: dict[str, QThread] = {}
        self._status_history: dict[str, deque[float]] = {}  # host -> deque of recent latencies
        self._current_status: dict[str, PingStatus] = {}
        self._failure_times: dict[str, list[str]] = {}  # host -> list of failure timestamps
        self._history_window_size = 10  # Number of recent pings to track for status determination

    def start_ping(self, host: str, interval_ms: int = 1000) -> None:
        """Start pinging a host. If already pinging, update interval."""
        if host in self._workers:
            return

        self._status_history[host] = deque(maxlen=self._history_window_size)
        self._current_status[host] = PingStatus.OK
        self._failure_times[host] = []

        thread = QThread()
        worker = _PingWorker(host, interval_ms)
        worker.moveToThread(thread)

        worker.result_ready.connect(lambda h, lat: self._on_result(h, lat))
        worker.raw_output.connect(lambda h, line: self.device_raw_output.emit(h, line))
        worker.error.connect(lambda h, err: self._on_error(h, err))
        worker.finished.connect(lambda h: self._on_worker_finished(h))

        thread.started.connect(worker.run)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)

        self._workers[host] = worker
        self._threads[host] = thread

        thread.start()
        self.device_started.emit(host)

    def stop_ping(self, host: str, wait: bool = False) -> None:
        """Stop pinging a host.

        Args:
            wait: If True, blocks until the thread has fully stopped
                  and cleanup is completed.
        """
        worker = self._workers.get(host)
        if worker is not None:
            worker.stop()

        thread = self._threads.get(host)
        if wait and thread is not None:
            if thread.isRunning():
                thread.quit()
                thread.wait(3000)
            # Direct cleanup: worker.finished is a queued signal (different thread),
            # so we clean up synchronously here to avoid relying on the event loop.
            self._cleanup_worker(host)

    def _cleanup_worker(self, host: str) -> None:
        """Remove worker/thread references and emit device_stopped."""
        self._workers.pop(host, None)
        self._threads.pop(host, None)
        self.device_stopped.emit(host)

    def stop_all(self, wait: bool = True) -> None:
        """Stop all ping workers.

        Args:
            wait: If True, blocks until all threads have fully terminated.
                  Set to False if calling from non-main thread or during cleanup.
        """
        hosts = list(self._workers.keys())
        for host in hosts:
            self.stop_ping(host)
        if wait:
            self._wait_for_all()

    def is_pinging(self, host: str) -> bool:
        """Check if pinging is active for a host."""
        return host in self._workers

    def get_current_status(self, host: str) -> PingStatus | None:
        """Get the current status for a host."""
        return self._current_status.get(host)

    def get_failure_log(self, host: str) -> list[str]:
        """Get the failure log for a host."""
        return self._failure_times.get(host, [])

    def _on_result(self, host: str, latency: float) -> None:
        """Handle a ping result."""
        if host not in self._status_history:
            return

        history = self._status_history[host]
        history.append(latency)

        self.device_latency.emit(host, latency)

        if latency <= 0:
            # Failure
            now = datetime.now(UTC).isoformat()
            self._failure_times.setdefault(host, []).append(now)
            self.device_failure_log.emit(host, now)

        # Determine status based on recent history
        new_status = self._determine_status(host)
        old_status = self._current_status.get(host)
        if new_status != old_status:
            self._current_status[host] = new_status
            self.device_status_changed.emit(host, new_status)

    def _on_error(self, host: str, error_message: str) -> None:
        """Handle a ping error."""
        if host in self._current_status:
            self._current_status[host] = PingStatus.UNREACHABLE
            self.device_status_changed.emit(host, PingStatus.UNREACHABLE)
        self.device_error.emit(host, error_message)

    def _wait_for_all(self) -> None:
        """Block until all threads have fully terminated."""
        for host in list(self._threads.keys()):
            thread = self._threads.get(host)
            if thread is not None and thread.isRunning():
                thread.quit()
                thread.wait(5000)
            self._cleanup_worker(host)

    def _on_worker_finished(self, host: str) -> None:
        """Clean up worker and thread after it has finished."""
        thread = self._threads.pop(host, None)
        worker = self._workers.pop(host, None)
        if thread is None and worker is None:
            # Already cleaned up by stop_ping(wait=True)
            return
        self.device_stopped.emit(host)

    def _determine_status(self, host: str) -> PingStatus:
        """Determine the status based on recent history.

        Rules:
        - If the latest result is a failure (latency <= 0): RED (UNREACHABLE) immediately.
        - If the latest result is a success but there were failures in the recent window: YELLOW (INTERMITTENT).
        - If all results in the recent window are successes: GREEN (OK).
        - If no results yet (history empty): GREEN (OK) as default.
        """
        history = self._status_history.get(host)
        if not history or len(history) == 0:
            return PingStatus.OK

        # Check the latest result first - immediate fail = RED
        latest = history[-1]
        if latest <= 0:
            return PingStatus.UNREACHABLE

        # Latest was success, but check if there were any failures in the window
        failures = sum(1 for lat in history if lat <= 0)
        if failures == 0:
            return PingStatus.OK
        else:
            return PingStatus.INTERMITTENT
