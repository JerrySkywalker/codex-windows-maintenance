"""Bounded RFC6455 JSON-RPC client over the private managed control socket."""
import base64
import hashlib
import json
import os
import struct
import time

from candidate_mapping import require


class RPC:
    def __init__(self, sock, transcript):
        self.sock, self.transcript = sock, transcript
        self.number = 0
        self.pending = []
        self.fragment = bytearray()
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall(("GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n"
                      "Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
                      f"Sec-WebSocket-Key: {key}\r\n\r\n").encode())
        header = bytearray()
        while not header.endswith(b"\r\n\r\n"):
            header.extend(self.exact(1))
            require(len(header) < 16384, "Oversized upgrade response")
        lines = header.decode().split("\r\n")
        require(lines[0].split()[1] == "101", "WebSocket upgrade failed")
        headers = {line.split(":", 1)[0].lower(): line.split(":", 1)[1].strip()
                   for line in lines[1:] if ":" in line}
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        require(headers.get("sec-websocket-accept") == accept, "Invalid WebSocket peer response")

    def exact(self, size):
        result = bytearray()
        while len(result) < size:
            chunk = self.sock.recv(size - len(result))
            require(chunk, "Managed socket closed unexpectedly")
            result.extend(chunk)
        return bytes(result)

    def frame(self, payload, opcode=1):
        mask = os.urandom(4)
        size = len(payload)
        prefix = bytes([0x80 | opcode, 0x80 | min(size, 126)])
        require(size < 65536, "Oversized client frame")
        if size >= 126:
            prefix += struct.pack("!H", size)
        self.sock.sendall(prefix + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def send(self, message):
        self.transcript.write(json.dumps({"direction": "send", "message": message}) + "\n")
        self.transcript.flush()
        self.frame(json.dumps(message).encode())

    def receive(self, deadline):
        while True:
            self.sock.settimeout(max(.01, deadline - time.monotonic()))
            first, second = self.exact(2)
            require(not second & 0x80, "Server frame unexpectedly masked")
            size = second & 127
            if size == 126:
                size = struct.unpack("!H", self.exact(2))[0]
            elif size == 127:
                size = struct.unpack("!Q", self.exact(8))[0]
            require(size <= 8 * 1024 * 1024, "Oversized server frame")
            payload = self.exact(size)
            opcode = first & 15
            if opcode == 9:
                self.frame(payload, 10)
                continue
            if opcode == 10:
                continue
            require(opcode in (0, 1), "Unexpected server frame")
            self.fragment.extend(payload)
            require(len(self.fragment) <= 8 * 1024 * 1024, "Oversized fragmented message")
            if not first & 0x80:
                continue
            message = json.loads(self.fragment)
            self.fragment.clear()
            self.transcript.write(json.dumps({"direction": "receive", "message": message}) + "\n")
            self.transcript.flush()
            require("method" not in message or "id" not in message, "Unexpected server approval/request")
            return message

    def call(self, method, params, timeout=30):
        self.number += 1
        self.send({"id": self.number, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self.receive(deadline)
            if message.get("id") == self.number:
                require("error" not in message, f"RPC {method} failed: {message.get('error')}")
                return message["result"]
            self.pending.append(message)
        raise TimeoutError(method)

    def completed_turn(self, thread_id, turn_id):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            message = self.pending.pop(0) if self.pending else self.receive(deadline)
            if message.get("method") == "turn/completed":
                params = message["params"]
                if params["threadId"] == thread_id and params["turn"]["id"] == turn_id:
                    require(params["turn"]["status"] == "completed" and not params["turn"].get("error"), "Managed turn failed")
                    return
        raise TimeoutError("Managed turn completion")

    def close(self):
        try:
            self.frame(b"", 8)
        finally:
            self.sock.close()
