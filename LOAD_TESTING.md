# Load Testing

## Setup
- Tool: [Locust](https://locust.io/)
- Target: local FastAPI backend + Postgres (Docker) + Redis
- Load: 50 concurrent users, spawn rate 10/s, 60s duration
- Endpoints exercised: `POST /seats/{id}/hold`, `POST /seats/{id}/confirm`

## Command

Locust pulls in gevent and flask, so it is not in `requirements-dev.txt`. Install it
when you want to run this:

```bash
pip install locust
locust -f locustfile.py --host=http://localhost:8000 --headless -u 50 -r 10 -t 60s --csv=loadtest
```

Rate limiting is on by default and will drown the run in 429s. Raise the limit or
disable the middleware before measuring throughput.

## Results

| Metric | Value |
|---|---|
| Total requests | 4459 |
| Failures | 0 |
| Throughput | 18.7 req/s |
| Median latency | 320 ms |
| p95 latency | 570 ms |
| p99 latency | 930 ms |
| Max latency | 2024 ms |

## Notes

- Zero failed requests under sustained load. The atomic UPDATE and the idempotency-key
  confirm path held up, with no double-booking and no duplicate-confirm errors.
- Most `confirm` requests return `confirmed: false` here, because the locustfile aims at
  random seat/user pairs rather than confirming a seat the same simulated user is holding.
  This measures latency and throughput under load, not booking success rate. Correctness is
  what the concurrency tests cover.
- The likely bottleneck is the synchronous psycopg driver blocking the event loop under
  concurrent load. That tradeoff is listed under known limitations in the README.
