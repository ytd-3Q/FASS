import json
import sys


def main() -> int:
    line = sys.stdin.readline()
    if not line:
        return 0
    payload = json.loads(line)
    name = payload.get("name") or "world"
    out = {"ok": True, "message": f"hello, {name}", "echo": payload}
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

