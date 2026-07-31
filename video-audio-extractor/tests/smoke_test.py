from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.cache_auditor import run_audit


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = root / "reports" / "audit_smoke"

        def mutate() -> None:
            time.sleep(0.4)
            target = root / "candidate.mp3"
            target.write_bytes(b"ID3" + b"\x00" * 4096)
            time.sleep(0.4)
            target.write_bytes(b"ID3" + b"\x01" * 8192)

        worker = threading.Thread(target=mutate)
        worker.start()
        report = run_audit([str(root)], duration=1.5, interval=0.2, out_prefix=str(out), probe_min_kb=256)
        worker.join()
        assert report["events"], "expected at least one cache event"
        assert Path(report["outputs"]["json"]).exists()
        assert Path(report["outputs"]["csv"]).exists()
        assert Path(report["outputs"]["markdown"]).exists()
    print("smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
