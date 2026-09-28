import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def sse(events):
    chunks = []
    for event in events:
        kind = event["type"]
        chunks.append(f"event: {kind}\n")
        chunks.append(f"data: {json.dumps(event, separators=(',', ':'))}\n\n")
    return "".join(chunks).encode("utf-8")


def created(response_id):
    return {"type": "response.created", "response": {"id": response_id}}


def completed(response_id):
    return {
        "type": "response.completed",
        "response": {
            "id": response_id,
            "usage": {
                "input_tokens": 0,
                "input_tokens_details": None,
                "output_tokens": 0,
                "output_tokens_details": None,
                "total_tokens": 0,
            },
        },
    }


def function_call(response_id, call_id, command, tool_mode="shell"):
    arguments = json.dumps(
        {"cmd": command, "yield_time_ms": 10000, "max_output_tokens": 2000},
        separators=(",", ":"),
    )
    item = {
        "type": "function_call", "call_id": call_id,
        "name": "exec_command", "arguments": arguments,
    }
    if tool_mode == "code_mode_only":
        item = {
            "type": "custom_tool_call", "call_id": call_id, "name": "exec",
            "input": "text(JSON.stringify(await tools.exec_command(" + arguments + ")));",
        }
    return sse(
        [
            created(response_id),
            {
                "type": "response.output_item.done",
                "item": item,
            },
            completed(response_id),
        ]
    )


def assistant_message(response_id):
    return sse(
        [
            created(response_id),
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "id": "msg-final",
                    "content": [{"type": "output_text", "text": "package smoke complete"}],
                },
            },
            completed(response_id),
        ]
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port-file", required=True)
    parser.add_argument("--request-log", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--shell-marker", required=True)
    parser.add_argument("--tool-mode", choices=("shell", "code_mode_only"), default="shell")
    parser.add_argument("--powershell", default="powershell")
    parser.add_argument("--python")
    parser.add_argument("--rg")
    args = parser.parse_args()

    port_file = Path(args.port_file)
    request_log = Path(args.request_log)
    workspace = Path(args.workspace)
    shell_marker = Path(args.shell_marker)
    state = {"count": 0}

    quoted_shell_marker = str(shell_marker).replace("'", "''")
    shell_program = "powershell" if args.powershell == "powershell" else '& "' + args.powershell + '"'
    shell_command = (
        shell_program + " -NoProfile -Command \"Set-Content -LiteralPath "
        f"'{quoted_shell_marker}' "
        "-Value 'shell-ok' -Encoding utf8\""
    )
    commands = [
        shell_command,
        "git rev-parse --show-toplevel",
        "where.exe rg",
    ]
    if args.tool_mode == "code_mode_only":
        if not args.python or not args.rg:
            parser.error("--python and --rg required for managed Code Mode smoke")
        probe = Path(__file__).with_name("bundled_rg_probe.py")
        commands[2] = '& "' + args.python + '" "' + str(probe) + '" "' + args.rg + '"'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_values):
            return

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {"raw": raw.decode("utf-8", errors="replace")}
            state["count"] += 1
            sequence = state["count"]
            with request_log.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {"sequence": sequence, "path": self.path, "body": body},
                        separators=(",", ":"),
                    )
                    + "\n"
                )

            if sequence <= len(commands):
                payload = function_call(
                    f"resp-{sequence}", f"call-{sequence}", commands[sequence - 1], args.tool_mode
                )
            else:
                payload = assistant_message(f"resp-{sequence}")

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            self.wfile.flush()

            if sequence >= 4:
                threading.Thread(target=self.server.shutdown, daemon=True).start()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port_file.write_text(str(server.server_address[1]), encoding="ascii")
    server.serve_forever()
    server.server_close()


if __name__ == "__main__":
    main()
