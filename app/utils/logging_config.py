"""Application logging configuration.

This module configures Loguru as the single logging sink for both:
- Application logs emitted through Loguru directly.
- Standard-library logging (including third-party libraries like Uvicorn),
  redirected via ``InterceptHandler``.

Current policy:
- Format: structured JSON Lines (``.jsonl``) using ``serialize=True``.
- Filename: ``{app_name}_YYYY-MM-DD.jsonl``.
- Rotation: daily at ``00:00`` local time, or earlier when file exceeds
  ``LOG_MAX_FILE_SIZE_BYTES`` (default: 50 MiB).
- Retention: ``14 days``.
- Compression: ``zip`` for rotated files.
- Windows log directory: ``%LOCALAPPDATA%\\{app_name}\\logs``.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
import sys
import threading
import tomllib
from pathlib import Path
from types import FrameType
from typing import Any, Callable

from loguru import logger as loguru_logger

DEFAULT_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame: FrameType | None = logging.currentframe()
        depth = 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        loguru_logger.bind(logger_name=record.name).opt(
            depth=depth,
            exception=record.exc_info,
        ).log(level, record.getMessage())


def configure_logging(level: str = 'INFO') -> Path:
    app_name = _sanitize_name(_resolve_app_name())
    log_dir = _default_log_dir(app_name)
    log_dir.mkdir(parents=True, exist_ok=True)
    max_file_size_bytes = _max_file_size_bytes()

    loguru_logger.remove()
    loguru_logger.configure(extra={'app': app_name})

    loguru_logger.add(
        (log_dir / f'{app_name}_{{time:YYYY-MM-DD}}.jsonl').as_posix(),
        level=level.upper(),
        serialize=True,
        rotation=_build_rotation_predicate(max_file_size_bytes=max_file_size_bytes),
        retention='14 days',
        compression='zip',
        enqueue=False,
        backtrace=False,
        diagnose=False,
        encoding='utf-8',
    )

    if _is_stream_usable(sys.stderr):
        loguru_logger.add(
            sys.stderr,
            level=level.upper(),
            format=(
                '<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | '
                '<level>{level: <8}</level> | '
                '<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - '
                '<level>{message}</level>'
            ),
            enqueue=False,
        )

    intercept_handler = InterceptHandler()
    logging.basicConfig(handlers=[intercept_handler], level=0, force=True)
    logging.captureWarnings(True)

    for logger_name in ('uvicorn', 'uvicorn.error', 'uvicorn.access'):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers = [intercept_handler]
        uvicorn_logger.propagate = False

    _install_uncaught_exception_hooks()

    return log_dir


def _default_log_dir(app_name: str) -> Path:
    if os.name == 'nt':
        local_app_data = os.getenv('LOCALAPPDATA')
        if local_app_data:
            return Path(local_app_data) / app_name / 'logs'
        return Path.home() / 'AppData' / 'Local' / app_name / 'logs'

    return Path.home() / '.local' / 'state' / app_name / 'logs'


def _resolve_app_name() -> str:
    env_name = os.getenv('APP_NAME')
    if env_name:
        return env_name

    pyproject_name = _read_project_name_from_pyproject()
    if pyproject_name:
        return pyproject_name

    executable_stem = Path(sys.argv[0]).stem
    return executable_stem or 'application'


def _read_project_name_from_pyproject() -> str | None:
    candidates = [
        Path.cwd() / 'pyproject.toml',
        Path(__file__).resolve().parents[2] / 'pyproject.toml',
    ]

    for candidate in candidates:
        if not candidate.exists():
            continue

        try:
            content = tomllib.loads(candidate.read_text(encoding='utf-8'))
        except OSError, tomllib.TOMLDecodeError:
            continue

        project_section = content.get('project')
        if not isinstance(project_section, dict):
            continue

        name = project_section.get('name')
        if isinstance(name, str) and name.strip():
            return name.strip()

    return None


def _sanitize_name(raw_name: str) -> str:
    sanitized = re.sub(r'[^A-Za-z0-9._-]+', '-', raw_name.strip())
    return sanitized.strip('-') or 'application'


def _max_file_size_bytes() -> int:
    raw = os.getenv('LOG_MAX_FILE_SIZE_BYTES')
    if raw is None:
        return DEFAULT_MAX_FILE_SIZE_BYTES

    try:
        parsed = int(raw)
    except ValueError:
        return DEFAULT_MAX_FILE_SIZE_BYTES

    return parsed if parsed > 0 else DEFAULT_MAX_FILE_SIZE_BYTES


def _build_rotation_predicate(max_file_size_bytes: int) -> Callable[[Any, Any], bool]:
    def _should_rotate(message: Any, file: Any) -> bool:
        message_time = message.record['time']
        file_date = _date_from_filename(Path(file.name).name)
        rotate_on_midnight = file_date is not None and message_time.date() != file_date
        rotate_on_size = file.tell() + len(message) > max_file_size_bytes
        return bool(rotate_on_midnight or rotate_on_size)

    return _should_rotate


def _date_from_filename(filename: str) -> dt.date | None:
    match = re.search(r'_(\d{4}-\d{2}-\d{2})', filename)
    if not match:
        return None

    try:
        return dt.date.fromisoformat(match.group(1))
    except ValueError:
        return None


def _is_stream_usable(stream: Any) -> bool:
    if stream is None:
        return False

    try:
        if bool(stream.closed):
            return False

        stream_name = getattr(stream, 'name', None)
        if isinstance(stream_name, str) and stream_name:
            return os.path.normcase(stream_name) != os.path.normcase(os.devnull)

        return True
    except Exception:
        return False


def _install_uncaught_exception_hooks() -> None:
    def _log_excepthook(
        exc_type: type[BaseException], exc_value: BaseException, exc_traceback: Any
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        loguru_logger.opt(exception=(exc_type, exc_value, exc_traceback)).critical(
            'Uncaught exception in main thread.'
        )

    def _threading_excepthook(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is None or args.exc_value is None:
            return

        if issubclass(args.exc_type, KeyboardInterrupt):
            return

        thread_name = args.thread.name if args.thread is not None else 'unknown-thread'
        loguru_logger.bind(thread=thread_name).opt(
            exception=(args.exc_type, args.exc_value, args.exc_traceback)
        ).critical('Uncaught exception in background thread.')

    sys.excepthook = _log_excepthook
    threading.excepthook = _threading_excepthook
