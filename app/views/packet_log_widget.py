"""Reusable packet log widget displaying data in a Wireshark-inspired view."""

from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


def _format_hex_ascii(data: bytes, max_bytes: int = 32) -> tuple[str, str]:
    """Format bytes as hex dump and ASCII representation."""
    hex_parts = []
    ascii_parts = []
    for i, b in enumerate(data[:max_bytes]):
        hex_parts.append(f'{b:02X}')
        ascii_parts.append(chr(b) if 32 <= b <= 126 else '.')
    hex_str = ' '.join(hex_parts)
    ascii_str = ''.join(ascii_parts)
    if len(data) > max_bytes:
        hex_str += ' ...'
        ascii_str += '...'
    return hex_str, ascii_str


class PacketLogWidget(QWidget):
    """A table widget that displays network packets in a Wireshark-inspired layout."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ['Time', 'Direction', 'Length', 'Source', 'Hex Dump', 'ASCII']
        )

        header = self._table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        self._table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

        # Monospace font for hex dump
        mono_font = QFont('Consolas', 9)
        mono_font.setStyleHint(QFont.StyleHint.Monospace)

        layout.addWidget(self._table)

        self._max_rows = 10000
        self._auto_scroll = True

        # Connect scrollbar to track auto-scroll
        scrollbar = self._table.verticalScrollBar()
        scrollbar.valueChanged.connect(self._on_scroll_changed)

    def set_auto_scroll(self, enabled: bool) -> None:
        """Enable or disable auto-scroll to bottom on new data."""
        self._auto_scroll = enabled

    def add_packet(
        self,
        direction: str,
        data: bytes,
        source: str = '',
        timestamp: str | None = None,
    ) -> None:
        """Add a packet entry to the log."""
        if timestamp is None:
            timestamp = datetime.now(UTC).isoformat()

        # Format timestamp for display
        try:
            dt = datetime.fromisoformat(timestamp)
            time_str = dt.astimezone().strftime('%H:%M:%S.%f')[:12]
        except (ValueError, TypeError):
            time_str = timestamp

        hex_str, ascii_str = _format_hex_ascii(data)
        length = len(data)

        row = self._table.rowCount()
        self._table.insertRow(row)

        # Time
        time_item = QTableWidgetItem(time_str)
        time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, 0, time_item)

        # Direction
        dir_item = QTableWidgetItem(direction)
        dir_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if direction in ('TX', 'SENT', '→'):
            dir_item.setForeground(QColor('#2196F3'))  # Blue for sent
        else:
            dir_item.setForeground(QColor('#4CAF50'))  # Green for received
        self._table.setItem(row, 1, dir_item)

        # Length
        len_item = QTableWidgetItem(str(length))
        len_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, 2, len_item)

        # Source
        src_item = QTableWidgetItem(source)
        self._table.setItem(row, 3, src_item)

        # Hex Dump
        hex_item = QTableWidgetItem(hex_str)
        mono_font = QFont('Consolas', 9)
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        hex_item.setFont(mono_font)
        self._table.setItem(row, 4, hex_item)

        # ASCII
        ascii_item = QTableWidgetItem(ascii_str)
        ascii_item.setFont(mono_font)
        self._table.setItem(row, 5, ascii_item)

        # Auto-scroll
        if self._auto_scroll:
            self._table.scrollToBottom()

        # Trim excess rows
        while self._table.rowCount() > self._max_rows:
            self._table.removeRow(0)

    def clear_log(self) -> None:
        """Clear all packet entries."""
        self._table.setRowCount(0)

    def _on_scroll_changed(self, value: int) -> None:
        """Track whether user wants auto-scroll based on scroll position."""
        scrollbar = self._table.verticalScrollBar()
        is_at_bottom = value >= scrollbar.maximum() - 10
        self._auto_scroll = is_at_bottom
