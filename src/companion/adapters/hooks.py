"""Generic local hook adapter: complete JSON events in, inbox events out."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TextIO

from ..protocol import ProtocolError, validate_event
from ..queue import append_jsonl


def forward_stream(stream: TextIO, inbox: Path, output: TextIO) -> int:
    """Forward valid complete event lines and report each result as JSON."""
    forwarded = 0
    for line_number, line in enumerate(stream, start=1):
        if not line.strip():
            continue
        try:
            event = validate_event(json.loads(line))
            append_jsonl(inbox, event)
            output.write(json.dumps({"line": line_number, "status": "queued", "event_id": event["id"]}) + "\n")
            forwarded += 1
        except (json.JSONDecodeError, ProtocolError) as exc:
            output.write(json.dumps({"line": line_number, "status": "error", "error": str(exc)}) + "\n")
    output.flush()
    return forwarded
