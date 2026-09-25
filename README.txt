Customer Platform Demo
======================

A tiny test repository for the LigoFlow release scenario. It is not a real
customer platform and does not contain customer data or credentials.

Files:
  app.py             HTTP API with a Redis-backed request limit
  redis_config.json  Redis connection and rate-limit settings for future PRs

To run it locally, start your own Redis server, install requirements.txt,
then run `python app.py`. GET /health checks the Redis connection.
GET /api/requests?client_id=demo exercises the limit.

The Redis URL may be overridden with REDIS_URL. No staging or production
deployment is implied by commits or pull requests in this repository.

Rate-limit rejection alerts are logged once the shared rejection counter
reaches RATE_LIMIT_ALERT_REJECTIONS (default: 10) within the configured Redis
window. Set RATE_LIMIT_ALERT_WEBHOOK_URL to deliver the JSON alert by HTTP POST.
If it is unset or delivery fails, the error is logged; API responses are not
blocked by alert delivery. This demo does not configure an on-call owner or
production monitoring destination.

The manually dispatched GitHub Actions QA staging workflow exercises an
ephemeral runner with its own Redis service for 120 seconds and records a
synthetic evidence artifact. It is not a customer staging deployment, an
on-call alert destination, or a production release approval.
