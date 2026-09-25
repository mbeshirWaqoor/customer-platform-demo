"""Small customer-platform API used only for the LigoFlow release scenario."""

import json
import logging
import os
from threading import Thread
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

import redis


CONFIG = json.loads((Path(__file__).parent / "redis_config.json").read_text())
LOGGER = logging.getLogger("customer_platform_demo")
ALERT_REJECTION_THRESHOLD = int(os.getenv("RATE_LIMIT_ALERT_REJECTIONS", "10"))
if ALERT_REJECTION_THRESHOLD < 1:
    raise ValueError("RATE_LIMIT_ALERT_REJECTIONS must be positive")
ALERT_WEBHOOK_URL = os.getenv("RATE_LIMIT_ALERT_WEBHOOK_URL", "").strip()
CLIENT = redis.Redis.from_url(
    os.getenv("REDIS_URL", CONFIG["url"]),
    socket_connect_timeout=CONFIG["connect_timeout_seconds"],
    socket_timeout=CONFIG["connect_timeout_seconds"],
)
LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local rejected = 0
if count > tonumber(ARGV[2]) then
  rejected = redis.call('INCR', KEYS[2])
  if rejected == 1 then redis.call('EXPIRE', KEYS[2], ARGV[1]) end
end
return {count, redis.call('TTL', KEYS[1]), rejected}
"""


def deliver_rate_limit_alert(alert: dict) -> None:
    request = Request(
        ALERT_WEBHOOK_URL,
        data=json.dumps(alert).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=2) as response:
            if response.status < 200 or response.status >= 300:
                LOGGER.error("rate_limit_alert_delivery_failed status=%s", response.status)
                return
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        LOGGER.error("rate_limit_alert_delivery_failed error=%s", type(error).__name__)
        return
    LOGGER.warning("rate_limit_alert_delivered")


def report_rate_limit_alert(rejected: int) -> None:
    alert = {
        "event": "rate_limit_rejections_threshold",
        "rejections": rejected,
        "threshold": ALERT_REJECTION_THRESHOLD,
        "window_seconds": CONFIG["rate_limit_window_seconds"],
    }
    LOGGER.warning("rate_limit_alert %s", json.dumps(alert, sort_keys=True))
    if not ALERT_WEBHOOK_URL:
        LOGGER.error("rate_limit_alert_delivery_unconfigured")
        return
    try:
        Thread(target=deliver_rate_limit_alert, args=(alert,), daemon=True).start()
    except RuntimeError:
        LOGGER.error("rate_limit_alert_delivery_failed error=thread_start")


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
            count, ttl, rejected = CLIENT.eval(
                LIMIT_SCRIPT,
                2,
                key,
                "customer-platform-demo:rate-limit-rejections",
                CONFIG["rate_limit_window_seconds"],
                CONFIG["rate_limit_requests"],
            )
        except redis.RedisError:
            self.send_json(503, {"error": "redis_unavailable"})
            return
        limit = CONFIG["rate_limit_requests"]
        if count > limit:
            if rejected == ALERT_REJECTION_THRESHOLD:
                report_rate_limit_alert(rejected)
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
