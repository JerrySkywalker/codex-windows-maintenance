import json
import sys
from datetime import datetime, timezone
from pathlib import Path


log_path = Path(sys.argv[1])
payload = json.load(sys.stdin)
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(
        json.dumps(
            {
                "utc": datetime.now(timezone.utc).isoformat(),
                "event": "hook",
                "payload": payload,
            },
            separators=(",", ":"),
        )
        + "\n"
    )
print(json.dumps({"continue": True}, separators=(",", ":")))
