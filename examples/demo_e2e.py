"""End-to-end demo: pack + message + reminder, no GUI, no network."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from companion.cli import main  # noqa: E402


def run(root: Path, *args: str) -> str:
    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    code = None
    with redirect_stdout(buffer):
        code = main(["--root", str(root), *args])
    assert code == 0, f"command failed: {args} -> {code}"
    return buffer.getvalue().strip()


def main_demo() -> int:
    with tempfile.TemporaryDirectory(prefix="companion-demo-") as tmp:
        root = Path(tmp)
        print(f"root={root}")
        print(run(root, "init"))
        print(run(root, "pack", "validate", str(ROOT / "examples" / "example-cat")))
        print(run(root, "--agent", "demo", "say", "Demo lista", "--ttl", "8"))
        now = datetime.now(timezone.utc).isoformat()
        print(run(root, "remind", "add", "--at", now, "--message", "Recordatorio demo"))
        print(run(root, "run", "--once"))
        status = run(root, "status")
        print(status)
        message = json.loads(status)["message"]
        assert message and message["text"] in {"Demo lista", "Recordatorio demo"}
        print(run(root, "doctor"))
        print("demo OK: pack + say + reminder through one pipeline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_demo())
