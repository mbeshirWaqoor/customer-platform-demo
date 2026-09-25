"""Small customer-platform API used only for the LigoFlow release scenario."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import redis


CONFIG = json.loads((Path(__file__).parent / "redis_config.json").read_text())
CLIENT = redis.Redis.from_url(
    os.getenv("REDIS_URL", CONFIG["url"]),
    socket_connect_timeout=CONFIG["connect_timeout_seconds"],
    socket_timeout=CONFIG["connect_timeout_seconds"],
)
LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return {count, redis.call('TTL', KEYS[1])}
"""


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status: int, payload: dict, headers: dict | None = None) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, str(value))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        request = urlsplit(self.path)
        if request.path == "/health":
            try:
                CLIENT.ping()
            except redis.RedisError:
                self.send_json(503, {"status": "redis_unavailable"})
                return
            self.send_json(200, {"status": "ok"})
            return
        if request.path != "/api/requests":
            self.send_json(404, {"error": "not_found"})
            return

        client_id = parse_qs(request.query).get("client_id", [""])[0]
        if not client_id or len(client_id) > 64 or not all(
            character.isascii() and (character.isalnum() or character in "_-")
            for character in client_id
        ):
            self.send_json(400, {"error": "invalid_client_id"})
            return
        key = f"customer-platform-demo:limit:{client_id}"
        try:
            count, ttl = CLIENT.eval(
                LIMIT_SCRIPT, 1, key, CONFIG["rate_limit_window_seconds"]
            )
        except redis.RedisError:
            self.send_json(503, {"error": "redis_unavailable"})
            return
        limit = CONFIG["rate_limit_requests"]
        if count > limit:
            self.send_json(
                429,
                {"error": "rate_limited"},
                {"Retry-After": max(1, ttl)},
            )
            return
        self.send_json(200, {"status": "accepted", "remaining": limit - count})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
