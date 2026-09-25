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
