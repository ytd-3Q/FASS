import json
import sys
from pathlib import Path


def main() -> int:
    line = sys.stdin.readline()
    if not line:
        return 0
    payload = json.loads(line)
    path = str(payload.get("path") or "note.txt")
    content = str(payload.get("content") or "")

    base = Path(__file__).resolve().parents[2] / "data" / "external"
    base.mkdir(parents=True, exist_ok=True)
    out_path = base / path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")

    sys.stdout.write(json.dumps({"ok": True, "path": str(out_path), "content": content}, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

