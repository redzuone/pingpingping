from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QSettings

from app.constants import APP_ID, APP_ORGANIZATION


@dataclass
class PingDeviceConfig:
    host: str = ''
    friendly_name: str = ''
    interval_ms: int = 1000
    enabled: bool = False


@dataclass
class QuickSendPreset:
    name: str = ''
    data: str = ''  # hex string or text
    encoding: str = 'hex'  # 'hex' or 'text'


@dataclass
class AppSettings:
    pinger_devices: list[PingDeviceConfig] = field(default_factory=list)
    pinger_auto_start: bool = True
    quick_send_presets: list[QuickSendPreset] = field(default_factory=list)
    tcp_connections: list[dict[str, Any]] = field(default_factory=list)
    udp_connections: list[dict[str, Any]] = field(default_factory=list)
    main_window_geometry: bytes | None = None
    main_window_state: bytes | None = None


def create_app_settings() -> QSettings:
    """Create user-scoped INI settings for the app."""
    return QSettings(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        APP_ORGANIZATION,
        APP_ID,
    )


def _coerce_float(value: object, fallback: float) -> float:
    if isinstance(value, (int, float, str)):
        try:
            return float(value)
        except (ValueError, TypeError):
            return fallback
    return fallback


def _coerce_int(value: object, fallback: int) -> int:
    if isinstance(value, (int, float, str)):
        try:
            return int(value)
        except (ValueError, TypeError):
            return fallback
    return fallback


def _coerce_bool(value: object, fallback: bool) -> bool:
    """Coerce a value to bool, handling QSettings string 'true'/'false'.

    QSettings stores bools as the strings 'true' or 'false'.
    Python's bool('false') is True (non-empty string), so we must
    compare explicitly.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes')
    if isinstance(value, (int, float)):
        return bool(value)
    return fallback


def load_settings(qs: QSettings) -> AppSettings:
    """Load persisted settings into a typed dataclass."""
    # Load pinger devices
    device_count = _coerce_int(qs.value('pinger/device_count', 0), 0)
    devices: list[PingDeviceConfig] = []
    for i in range(device_count):
        prefix = f'pinger/device/{i}'
        devices.append(
            PingDeviceConfig(
                host=str(qs.value(f'{prefix}/host', '')),
                friendly_name=str(qs.value(f'{prefix}/friendly_name', '')),
                interval_ms=_coerce_int(qs.value(f'{prefix}/interval_ms', 1000), 1000),
                enabled=_coerce_bool(qs.value(f'{prefix}/enabled', False), False),
            )
        )

    # Load quick send presets
    preset_count = _coerce_int(qs.value('quick_send/count', 0), 0)
    presets: list[QuickSendPreset] = []
    for i in range(preset_count):
        prefix = f'quick_send/preset/{i}'
        presets.append(
            QuickSendPreset(
                name=str(qs.value(f'{prefix}/name', '')),
                data=str(qs.value(f'{prefix}/data', '')),
                encoding=str(qs.value(f'{prefix}/encoding', 'hex')),
            )
        )

    # Load TCP connections
    tcp_count = _coerce_int(qs.value('tcp/connection_count', 0), 0)
    tcp_connections: list[dict[str, Any]] = []
    for i in range(tcp_count):
        prefix = f'tcp/connection/{i}'
        tcp_connections.append(
            {
                'name': str(qs.value(f'{prefix}/name', '')),
                'host': str(qs.value(f'{prefix}/host', '')),
                'port': _coerce_int(qs.value(f'{prefix}/port', 0), 0),
                'is_server': _coerce_bool(qs.value(f'{prefix}/is_server', False), False),
            }
        )

    # Load UDP connections
    udp_count = _coerce_int(qs.value('udp/connection_count', 0), 0)
    udp_connections: list[dict[str, Any]] = []
    for i in range(udp_count):
        prefix = f'udp/connection/{i}'
        udp_connections.append(
            {
                'name': str(qs.value(f'{prefix}/name', '')),
                'host': str(qs.value(f'{prefix}/host', '')),
                'port': _coerce_int(qs.value(f'{prefix}/port', 0), 0),
                'is_server': _coerce_bool(qs.value(f'{prefix}/is_server', False), False),
            }
        )

    return AppSettings(
        pinger_devices=devices,
        pinger_auto_start=_coerce_bool(qs.value('pinger/auto_start', True), True),
        quick_send_presets=presets,
        tcp_connections=tcp_connections,
        udp_connections=udp_connections,
    )


def save_settings(qs: QSettings, settings: AppSettings) -> None:
    """Persist the typed settings dataclass."""
    qs.clear()
    qs.sync()

    # Save pinger devices
    qs.setValue('pinger/device_count', len(settings.pinger_devices))
    for i, device in enumerate(settings.pinger_devices):
        prefix = f'pinger/device/{i}'
        qs.setValue(f'{prefix}/host', device.host)
        qs.setValue(f'{prefix}/friendly_name', device.friendly_name)
        qs.setValue(f'{prefix}/interval_ms', device.interval_ms)
        qs.setValue(f'{prefix}/enabled', device.enabled)

    qs.setValue('pinger/auto_start', settings.pinger_auto_start)

    # Save quick send presets
    qs.setValue('quick_send/count', len(settings.quick_send_presets))
    for i, preset in enumerate(settings.quick_send_presets):
        prefix = f'quick_send/preset/{i}'
        qs.setValue(f'{prefix}/name', preset.name)
        qs.setValue(f'{prefix}/data', preset.data)
        qs.setValue(f'{prefix}/encoding', preset.encoding)

    # Save TCP connections
    qs.setValue('tcp/connection_count', len(settings.tcp_connections))
    for i, conn in enumerate(settings.tcp_connections):
        prefix = f'tcp/connection/{i}'
        qs.setValue(f'{prefix}/name', conn.get('name', ''))
        qs.setValue(f'{prefix}/host', conn.get('host', ''))
        qs.setValue(f'{prefix}/port', conn.get('port', 0))
        qs.setValue(f'{prefix}/is_server', conn.get('is_server', False))

    # Save UDP connections
    qs.setValue('udp/connection_count', len(settings.udp_connections))
    for i, conn in enumerate(settings.udp_connections):
        prefix = f'udp/connection/{i}'
        qs.setValue(f'{prefix}/name', conn.get('name', ''))
        qs.setValue(f'{prefix}/host', conn.get('host', ''))
        qs.setValue(f'{prefix}/port', conn.get('port', 0))
        qs.setValue(f'{prefix}/is_server', conn.get('is_server', False))

    qs.sync()
