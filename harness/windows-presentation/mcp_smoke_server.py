import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


log_path = Path(sys.argv[1])


def record(event, **fields):
    payload = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":")) + "\n")


def respond(request_id, result):
    sys.stdout.write(
        json.dumps(
            {"jsonrpc": "2.0", "id": request_id, "result": result},
            separators=(",", ":"),
        )
        + "\n"
    )
    sys.stdout.flush()


record("start", pid=os.getpid())
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    message = json.loads(line)
    method = message.get("method", "")
    record("message", method=method, hasId="id" in message)
    if "id" not in message:
        continue
    if method == "initialize":
        version = message.get("params", {}).get("protocolVersion", "2025-06-18")
        respond(
            message["id"],
            {
                "protocolVersion": version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "wbp-package-smoke", "version": "1.0.0"},
            },
        )
    elif method == "tools/list":
        respond(message["id"], {"tools": []})
    elif method == "resources/list":
        respond(message["id"], {"resources": []})
    elif method == "prompts/list":
        respond(message["id"], {"prompts": []})
    else:
        respond(message["id"], {})

record("eof")
