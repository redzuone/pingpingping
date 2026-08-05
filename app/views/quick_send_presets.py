"""Quick-send preset manager widget for TCP/UDP tools."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.utils.app_settings import QuickSendPreset


class _PresetEditDialog(QDialog):
    """Dialog for adding/editing a quick-send preset."""

    def __init__(
        self,
        preset: QuickSendPreset | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle('Edit Preset' if preset else 'Add Preset')
        self.setModal(True)
        self._result_preset: QuickSendPreset | None = None

        name_label = QLabel('Name:')
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText('e.g., "Hello World"')

        data_label = QLabel('Data:')
        self._data_input = QLineEdit()
        self._data_input.setPlaceholderText('Hex bytes (e.g., 48656C6C6F) or text')

        self._hex_mode_btn = QPushButton('Hex')
        self._hex_mode_btn.setCheckable(True)
        self._hex_mode_btn.setChecked(True)
        self._text_mode_btn = QPushButton('Text')
        self._text_mode_btn.setCheckable(True)

        def _set_hex_mode() -> None:
            self._hex_mode_btn.setChecked(True)
            self._text_mode_btn.setChecked(False)

        def _set_text_mode() -> None:
            self._text_mode_btn.setChecked(True)
            self._hex_mode_btn.setChecked(False)

        self._hex_mode_btn.clicked.connect(_set_hex_mode)
        self._text_mode_btn.clicked.connect(_set_text_mode)

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel('Encoding:'))
        mode_layout.addWidget(self._hex_mode_btn)
        mode_layout.addWidget(self._text_mode_btn)
        mode_layout.addStretch()

        save_btn = QPushButton('Save')
        save_btn.clicked.connect(self._on_save)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)

        form_layout = QFormLayout()
        form_layout.addRow(name_label, self._name_input)
        form_layout.addRow(data_label, self._data_input)
        form_layout.addRow(mode_layout)

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(form_layout)
        main_layout.addLayout(btn_layout)

        if preset:
            self._name_input.setText(preset.name)
            self._data_input.setText(preset.data)
            if preset.encoding == 'text':
                self._text_mode_btn.setChecked(True)
                self._hex_mode_btn.setChecked(False)
            else:
                self._hex_mode_btn.setChecked(True)
                self._text_mode_btn.setChecked(False)

    def _on_save(self) -> None:
        name = self._name_input.text().strip()
        data = self._data_input.text().strip()
        if not name or not data:
            return
        encoding = 'hex' if self._hex_mode_btn.isChecked() else 'text'
        self._result_preset = QuickSendPreset(name=name, data=data, encoding=encoding)
        self.accept()

    def get_preset(self) -> QuickSendPreset | None:
        return self._result_preset


class QuickSendPresetsWidget(QWidget):
    """Widget that manages a list of quick-send presets with click-to-send buttons."""

    def __init__(
        self,
        presets: list[QuickSendPreset] | None = None,
        on_send: Callable[[bytes], None] | None = None,
        on_change: Callable[[list[QuickSendPreset]], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._presets: list[QuickSendPreset] = presets or []
        self._on_send_callback = on_send
        self._on_change_callback = on_change

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # The add-preset button is created here but not placed in this widget's
        # own layout — the parent view places it wherever fits its layout best.
        self._add_btn = QPushButton('+')
        self._add_btn.setFixedWidth(30)
        self._add_btn.setToolTip('Add a new preset')
        self._add_btn.clicked.connect(self._on_add_preset)

        self._preset_list = QListWidget()
        self._preset_list.setMaximumHeight(200)
        self._update_list()
        layout.addWidget(self._preset_list)

    @property
    def add_button(self) -> QPushButton:
        """The 'add preset' button, for the parent to place in its own layout."""
        return self._add_btn

    def set_on_send_callback(self, callback: Callable[[bytes], None]) -> None:
        """Set the callback for when a preset is clicked to send."""
        self._on_send_callback = callback

    def get_presets(self) -> list[QuickSendPreset]:
        """Get current presets."""
        return self._presets

    def set_presets(self, presets: list[QuickSendPreset]) -> None:
        """Replace all presets."""
        self._presets = presets
        self._update_list()

    def _update_list(self) -> None:
        """Rebuild the preset list widget."""
        self._preset_list.clear()
        for idx, preset in enumerate(self._presets):
            # Create a widget for each preset item
            item = QListWidgetItem()
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(4, 2, 4, 2)

            name_label = QLabel(preset.name)
            name_label.setStyleSheet('font-weight: bold; min-width: 80px;')

            data_preview = preset.data[:40]
            data_label = QLabel(f'[{preset.encoding.upper()}] {data_preview}')
            data_label.setStyleSheet('color: #888;')

            send_btn = QPushButton('Send')
            send_btn.setFixedWidth(50)
            send_btn.clicked.connect(lambda checked, p=preset: self._on_send_preset(p))

            edit_btn = QPushButton('✎')
            edit_btn.setFixedWidth(25)
            edit_btn.clicked.connect(lambda checked, i=idx: self._on_edit_preset_at(i))

            delete_btn = QPushButton('✕')
            delete_btn.setFixedWidth(25)
            delete_btn.clicked.connect(lambda checked, i=idx: self._on_delete_preset_at(i))

            layout.addWidget(name_label)
            layout.addWidget(data_label, 1)
            layout.addWidget(send_btn)
            layout.addWidget(edit_btn)
            layout.addWidget(delete_btn)

            item.setSizeHint(widget.sizeHint())
            self._preset_list.addItem(item)
            self._preset_list.setItemWidget(item, widget)

    def _on_add_preset(self) -> None:
        dialog = _PresetEditDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            preset = dialog.get_preset()
            if preset:
                self._presets.append(preset)
                self._update_list()
                self._notify_change()

    def _on_edit_preset_at(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._presets):
            return
        preset = self._presets[idx]
        dialog = _PresetEditDialog(preset=preset, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_preset = dialog.get_preset()
            if new_preset:
                self._presets[idx] = new_preset
                self._update_list()
                self._notify_change()

    def _on_delete_preset_at(self, idx: int) -> None:
        if 0 <= idx < len(self._presets):
            self._presets.pop(idx)
            self._update_list()
            self._notify_change()

    def _notify_change(self) -> None:
        if self._on_change_callback is not None:
            self._on_change_callback(self._presets)

    def _on_send_preset(self, preset: QuickSendPreset) -> None:
        if self._on_send_callback is None:
            return
        try:
            if preset.encoding == 'hex':
                # Remove whitespace and convert hex to bytes
                hex_str = preset.data.replace(' ', '').replace('\n', '').replace('\r', '')
                data = bytes.fromhex(hex_str)
            else:
                data = preset.data.encode('utf-8')
            self._on_send_callback(data)
        except ValueError as e:
            from loguru import logger
            logger.error(f'Failed to encode preset data: {e}')
