from __future__ import annotations

import json
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen

HEALTHCHECK_URL = "http://127.0.0.1:8732/healthz"


def main() -> int:
    request = Request(HEALTHCHECK_URL, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=5) as response:
            status = response.status
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError) as exc:
        print(f"healthcheck failed: {exc}", file=sys.stderr)
        return 1

    if status != 200 or payload != {"status": "ok"}:
        print(f"healthcheck failed: status={status} payload={payload!r}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
