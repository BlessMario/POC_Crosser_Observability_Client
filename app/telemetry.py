from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import (
    BatchLogRecordProcessor,
    LogExporter,
    LogExportResult,
)

from .config import settings


class FileLogExporter(LogExporter):
    def __init__(self, file_path: str):
        self._file_path = file_path
        self._lock = threading.Lock()

    def export(self, batch: Sequence) -> LogExportResult:
        try:
            lines: list[str] = []
            for item in batch:
                record = item.log_record
                severity = getattr(record.severity_text, "value", None) or str(record.severity_text)
                body = record.body
                if not isinstance(body, str):
                    body = str(body)
                attrs = {}
                if record.attributes:
                    attrs = {str(k): v for k, v in record.attributes.items()}

                ts_ns = getattr(record, "timestamp", None)
                if isinstance(ts_ns, int) and ts_ns > 0:
                    ts = datetime.fromtimestamp(ts_ns / 1_000_000_000, tz=timezone.utc).isoformat()
                else:
                    ts = datetime.now(timezone.utc).isoformat()

                payload = {
                    "ts": ts,
                    "severity": severity,
                    "body": body,
                    "attributes": attrs,
                }
                lines.append(json.dumps(payload, ensure_ascii=False))

            if not lines:
                return LogExportResult.SUCCESS

            with self._lock:
                with open(self._file_path, "a", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
            return LogExportResult.SUCCESS
        except Exception:
            return LogExportResult.FAILURE

    def shutdown(self):
        return None


def setup_observability() -> None:
    log_path = Path(settings.otel_log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(FileLogExporter(str(log_path))))

    handler = LoggingHandler(level=logging.NOTSET, logger_provider=provider)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    root_logger.addHandler(handler)

    # Keep stdout logs too for container-level troubleshooting.
    stream = logging.StreamHandler()
    stream.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    root_logger.addHandler(stream)

    logging.getLogger(__name__).info(
        "OpenTelemetry file logging initialized",
        extra={
            "otel_log_file": str(log_path),
            "pid": os.getpid(),
            "log_level": settings.log_level.upper(),
        },
    )
