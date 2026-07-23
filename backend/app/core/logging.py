from __future__ import annotations

import logging
from typing import Any

from backend.app.core.redaction import redact_payload


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        original_args: Any = record.args
        original_msg = record.msg
        record.msg = redact_payload(record.msg)
        record.args = redact_payload(record.args)
        try:
            return super().format(record)
        finally:
            record.msg = original_msg
            record.args = original_args
