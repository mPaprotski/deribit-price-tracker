# Deribit Price Tracker

## Overview

A backend that periodically collects BTC and ETH index prices from Deribit,
stores them in PostgreSQL, and exposes a read-only REST API.
The entire system runs with `docker compose up --build`.

## Features

- Collects `BTC_USD` and `ETH_USD` every 60 seconds by default.
- Returns complete history, the latest price, and history within a time range.
- Stores prices as PostgreSQL `NUMERIC` and serializes them as JSON strings.
- Continues collecting ETH when the BTC API request fails, and vice versa.
- Uses a Redis lock to prevent concurrent collection tasks.
- Includes Swagger documentation, unit tests, integration tests, and CI.

## Technology Stack

| Component | Technology |
| --- | --- |
| Runtime | Python 3.11+ |
| REST API / validation | FastAPI, Pydantic v2 |
| Database | PostgreSQL 16, SQLAlchemy async, asyncpg |
| HTTP client | aiohttp |
| Background collection | Celery Worker, Celery Beat, Redis 7.4 |
| Testing | pytest, pytest-asyncio, httpx, unittest.mock |
| Deployment / CI | Docker Compose, GitHub Actions |

Direct dependencies are listed in `requirements.in`; `requirements.txt` installs
the complete pinned dependency snapshot from `requirements.lock` (Python 3.11/3.12, Linux).
The Docker Python base image is pinned by digest.

## Architecture

```text
HTTP request -> FastAPI router -> PriceService -> PriceRepository -> PostgreSQL

Celery Beat -> Redis broker -> Celery Worker -> CollectorService
                                                |         |
                                          DeribitClient   PriceRepository
                                                |         |
                                            Deribit API   PostgreSQL
```

Routers contain HTTP concerns, services implement validation and collection,
and the repository implements SQLAlchemy queries. The task owns its Redis lock;
the collection runner owns its database transaction and HTTP session.

## Project Structure

```text
app/
  main.py                    # FastAPI entry point and domain error handlers
  celery_app.py              # Broker, task limits, and Beat schedule
  tasks.py                   # Collection task and Redis lock
  api/dependencies.py        # Database and service dependencies
  api/routes/prices.py       # Read endpoints
  core/                      # Environment settings and supported tickers
  db/                        # Declarative base, model, async engine/session
  schemas/price.py           # Response and query parameter schemas
  repositories/              # Database operations
  clients/                   # Deribit HTTP client
  services/                  # Price service, collector, resource lifecycle
scripts/
  init_db.py                 # Idempotent table creation
  collect_prices.py          # Manual collection
tests/                      # Unit and marked integration tests
.github/workflows/ci.yml
Dockerfile
docker-compose.yml
.env.example
requirements.in
requirements.lock
requirements.txt
pytest.ini
```

## Getting Started

### Docker Compose

Install Docker Engine and Docker Compose v2, then run from the repository root:

```bash
docker compose up --build
```

API: http://localhost:8000. Swagger: http://localhost:8000/docs.
If port 8000 is occupied, use `WEB_PORT=18000 docker compose up --build`.
For background execution with readiness checks:

```bash
docker compose up --build -d --wait
docker compose ps
docker compose logs -f celery_worker celery_beat
```

Five services are started: `db`, `redis`, `web`, `celery_worker`, `celery_beat`.
PostgreSQL and Redis ports are internal to the Docker network. API listens on
`127.0.0.1` on the host. Application containers run as UID 10001, not root.

`web` waits for PostgreSQL readiness and creates tables before starting Uvicorn.
Worker waits for the database, Redis, and healthy API; Beat waits for Redis and
healthy worker. All services have healthchecks and `unless-stopped` restart policies.
The first collection runs after the configured interval once Beat has started.
Run one Beat instance for this schedule.

```bash
docker compose exec db psql -U postgres -d deribit -c 'SELECT ticker, price, timestamp FROM price_records ORDER BY id DESC LIMIT 10;'
docker compose down
```

`down` preserves the `postgres_data` and `redis_data` named volumes. Redis uses AOF
persistence. Beat writes its local scheduler files under `/app/run`.
Compose defaults to development PostgreSQL credentials `postgres/postgres`, database
`deribit`. Set `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` before the
first initialization to change them. Existing PostgreSQL volumes retain their
original credentials; changing environment variables does not migrate users/passwords.

### Local development

Install Python 3.11+, PostgreSQL, and Redis. Create a PostgreSQL database named
`deribit`, then run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m scripts.init_db
python -m scripts.run_api --reload
```

In separate terminals with the same environment activated:

```bash
celery -A app.celery_app:celery_app worker --pool=prefork --concurrency=2 --loglevel=INFO
celery -A app.celery_app:celery_app beat --loglevel=INFO
```

For a single manual collection without Celery:

```bash
python -m scripts.collect_prices
```

To enqueue a collection using the running worker:

```bash
celery -A app.celery_app:celery_app call app.tasks.collect_prices_task
```

## Environment Variables

Settings are read from the repository's `.env`; process environment variables take
precedence. Defaults allow local development. `.env` is excluded from Git and images.

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/deribit` | Async PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker and collection lock |
| `DERIBIT_BASE_URL` | `https://www.deribit.com/api/v2` | Deribit API base URL |
| `COLLECTION_INTERVAL` | `60` | Positive collection interval in seconds |
| `LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR, CRITICAL |

Compose constructs its database URL from `POSTGRES_USER`, `POSTGRES_PASSWORD`,
and `POSTGRES_DB`, using hostname `db`. `COMPOSE_DATABASE_URL` overrides that full
URL; `COMPOSE_REDIS_URL` overrides the broker URL (default `redis://redis:6379/0`).
These separate settings avoid accidentally using local `localhost` URLs inside Docker.
For credentials containing URL-reserved characters, provide `COMPOSE_DATABASE_URL`
with percent-encoded username/password while leaving `POSTGRES_PASSWORD` unencoded.

Compose also reads `DERIBIT_BASE_URL`, `COLLECTION_INTERVAL`, and `LOG_LEVEL`.
Optional `WEB_PORT` controls the host API port (default 8000). All values can be set
in the environment or `.env`; `.env.example` lists the Compose overrides.
The API launcher applies `LOG_LEVEL` to application logs and Uvicorn startup/access
logs. For local use, run `python -m scripts.run_api --reload`; Docker uses the same launcher.

Tests use `TEST_DATABASE_URL` and `TEST_REDIS_URL` for dedicated test services;
these are independent of application connection settings.

## API Documentation

Swagger: `/docs`. OpenAPI schema: `/openapi.json`.
No API key is required for these read endpoints.

| Method | Path | Required query parameters | Success |
| --- | --- | --- | --- |
| GET | `/health` | None | `{"status":"ok"}` |
| GET | `/prices` | `ticker` | Array of price records |
| GET | `/prices/latest` | `ticker` | One price record |
| GET | `/prices/filter` | `ticker`, `start_time`, `end_time` | Array of price records |

Tickers are case-sensitive: `BTC_USD` or `ETH_USD`. Timestamps are non-negative
integer UNIX seconds bounded by PostgreSQL BIGINT. Both time boundaries are
inclusive; `start_time` must not exceed `end_time`.
History is ordered by `(timestamp, id)` ascending. Latest uses descending order,
with `id` breaking ties when timestamps match.

Example record:

```json
{"id": 1, "ticker": "BTC_USD", "price": "65000.123456789012345678", "timestamp": 1728000000}
```

`price` is always a decimal string, not a JSON floating-point number.
`id` and `timestamp` are integers.

## Examples

```bash
# BTC history: HTTP 200, possibly [] before the first collection
curl 'http://localhost:8000/prices?ticker=BTC_USD'

# Latest ETH price: HTTP 200 after collection, otherwise HTTP 404
curl 'http://localhost:8000/prices/latest?ticker=ETH_USD'

# History in an inclusive range; this historical example may return []
curl 'http://localhost:8000/prices/filter?ticker=BTC_USD&start_time=1728000000&end_time=1728086400'

# Missing ticker: HTTP 422
curl -i 'http://localhost:8000/prices'

# Reversed time range: HTTP 422
curl -i 'http://localhost:8000/prices/filter?ticker=BTC_USD&start_time=200&end_time=100'
```

## Running Tests

Unit tests mock Deribit HTTP calls, repositories, or task dependencies. They need
neither the exchange nor PostgreSQL/Redis. Compose configuration checks use the Docker
Compose CLI without starting containers (these checks skip if Docker is not installed):

```bash
python -m pytest -q -m 'not integration'
```

Integration tests have an explicit `integration` marker and use actual PostgreSQL
or Redis. Create an empty dedicated PostgreSQL database, then run:

```bash
export TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/deribit_test
export TEST_REDIS_URL=redis://localhost:6379/1
python -m pytest -q -m integration

# All tests
python -m pytest -q
```

Database changes roll back after each test. Use a dedicated empty database and a
separate Redis database: tests acquire the collection lock and create tables.
Integration tests skip when their test URL is absent; a configured but unavailable
service causes failure. No automated test contacts the live exchange.

| Test file | Coverage |
| --- | --- |
| `test_deribit_client.py` | Success, HTTP/network/time-out/JSON/RPC errors, invalid prices, HTTP session cleanup |
| `test_price_service.py` | Tickers, time ranges, missing data, repository delegation |
| `test_collector_service.py` | Both indexes, partial/total API failure, decimal conversion, cancellation |
| `test_price_repository.py` | PostgreSQL writes/reads, decimal precision, ordering, filtering, transactions, index |
| `test_prices_api.py` | HTTP 200/404/422, serialization, Swagger/OpenAPI, real repository integration |
| `test_tasks.py` | Schedule, lock ownership, overlap prevention, failure propagation, event loops, real Redis |
| `test_collection_runner.py` | Transaction rollback and HTTP/engine cleanup |
| `test_configuration.py` | API log level, Compose connection and credential overrides |
| `test_collection_pipeline.py` | Real task -> mocked HTTP -> collector -> PostgreSQL -> API, including partial/total API failure and repeated event loops |

GitHub Actions runs on push, pull request, or manual dispatch. Python 3.11 and
3.12 jobs validate Compose, install dependencies, run `pip check`, initialize the
schema twice, and run unit/integration tests in separate steps. PostgreSQL 16 and
Redis 7.4 are service containers. A separate CI job builds and starts the entire
Compose stack with custom database credentials, Beat and worker, and a deterministic
Deribit stub; it verifies periodic collection and all API endpoints. No automated
check requires the live exchange.

To reproduce the Compose end-to-end check locally (isolated project and test volumes):

```bash
WEB_PORT=18000 docker compose -p deribit-ci -f docker-compose.yml -f docker-compose.ci.yml up --build -d --wait
WEB_PORT=18000 python3 tests/support/check_compose.py
docker compose -p deribit-ci -f docker-compose.yml -f docker-compose.ci.yml down --volumes
```

The extra exchange-stub container exists only in the CI override; normal Compose
continues to run five services. No secrets or `.env` are required for CI.

To update dependencies, resolve `requirements.in` in a fresh Python virtual environment,
freeze the complete environment into `requirements.lock`, and run CI on both supported
Python versions. Normal installs always use `pip install -r requirements.txt`.

## Design Decisions

- **FastAPI:** typed async endpoints, dependency injection, query validation, and
  generated OpenAPI/Swagger keep the HTTP layer small.
- **Async HTTP:** aiohttp avoids blocking while waiting for Deribit. Related
  requests share a client session during one collection run; each has a 10-second timeout.
- **Celery and Redis:** Beat schedules work independently of API processes, workers
  execute it, and Redis provides the broker and collection lock.
- **Repository Pattern:** SQLAlchemy queries stay in `PriceRepository`. Services
  validate inputs and coordinate work through constructor-injected dependencies.
- **Dependency Injection:** FastAPI builds `PriceService(PriceRepository(session))`
  through `get_db`/`get_price_service`; tests override those dependencies. Collection
  receives a client and repository explicitly.
- **Connection lifecycle:** API requests receive their own transaction and session;
  application shutdown disposes its engine. Each Celery call uses `asyncio.run()`
  and creates/disposes its own async engine, database session, and HTTP session
  within that event loop. The repository flushes writes; the caller owns commit/rollback.
- **PostgreSQL:** durable relational storage, exact `NUMERIC`, transactional writes,
  and a composite `(ticker, timestamp)` index suit price history queries.
- **External API failures:** errors are typed and logged per ticker. One failing
  request does not stop the other. If neither price is retrieved, the task fails;
  the next scheduled invocation tries again. Database errors roll back the run.

## Error Handling

| Condition | Behavior |
| --- | --- |
| Missing or unsupported ticker | HTTP 422 |
| Invalid timestamp or reversed range | HTTP 422 |
| No latest price | HTTP 404 |
| Empty history or filtered result | HTTP 200 with `[]` |
| Deribit time-out, network or HTTP failure | Typed client error; logged by collector |
| Invalid JSON, JSON-RPC error, missing/non-positive/non-finite price | Typed client error; price is not stored |
| Both Deribit requests fail | `PriceCollectionError`; Celery task fails and logs the exception |
| Database write failure | Collection transaction rolls back; task fails |
| Another task holds the Redis lock | Collection is skipped without waiting |

Celery tasks use a 120-second token-owned lock, a 50-second soft limit and
60-second hard limit. The async collection runner has a 45-second timeout.
Use the prefork worker pool so Celery time limits apply. A crash leaves the lock
until its TTL expires. Redis lock release verifies ownership. If Redis is unavailable
during release, the error is logged and the task retains its original success/failure
result; the lock expires via TTL.

`/health` reports API process availability; it does not probe PostgreSQL, Redis,
or the exchange. Compose checks PostgreSQL/Redis readiness separately.

## Known Limitations

- History is unpaginated and has no retention policy.
- Only BTC_USD and ETH_USD are supported. Timestamps have second precision and
  represent local retrieval time, not exchange event time.
- The required client interface returns `float`. `Decimal(str(price))` avoids
  additional binary artifacts when storing it, but cannot recover digits already
  lost during float conversion. A fully exact ingestion pipeline would return Decimal.
- `create_all` initializes missing tables; it does not migrate existing schemas.
  Schema evolution requires migrations such as Alembic.
- One Beat instance is expected. The lock prevents concurrent execution, not
  sequential duplicate messages or an exactly-once delivery guarantee.
- The direct manual collection command bypasses the Celery lock.
- Automatic retries within a task are not configured; the next scheduled run retries collection.
- Default credentials and the read-only API are intended for the assignment/local use;
  authentication, TLS, monitoring, and production secrets management are not implemented.

References: [Deribit index-price API](https://test.deribit.com/api_console/?method=%2Fpublic%2Fget_index_price),
[FastAPI query models](https://fastapi.tiangolo.com/tutorial/query-param-models/),
[Celery periodic tasks](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html),
[Compose startup dependencies](https://docs.docker.com/compose/how-tos/startup-order/).
