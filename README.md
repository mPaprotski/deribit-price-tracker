# Deribit Price Tracker

Начальный каркас приложения на Python 3.11+ и FastAPI.

## Запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Проверка: `curl http://127.0.0.1:8000/health` возвращает HTTP 200
и `{"status":"ok"}`. Документация API: http://127.0.0.1:8000/docs.

Настройки читаются из `.env` в корне проекта; переменные окружения имеют
приоритет. `COLLECTION_INTERVAL` задаётся в секундах и должен быть больше нуля.
Уровни `LOG_LEVEL`: DEBUG, INFO, WARNING, ERROR, CRITICAL.

При запуске через Docker Compose замените `localhost` в `DATABASE_URL`
и `REDIS_URL` именами соответствующих сервисов, например `postgres` и `redis`.
`/health` проверяет доступность приложения. Redis и сбор цен будут добавлены
на следующих этапах.


## База данных

Создайте базу PostgreSQL `deribit` и настройте `DATABASE_URL` в `.env`.
Далее из корня проекта выполните:

```bash
python -m scripts.init_db
```

Скрипт создаёт таблицу `price_records` и составной индекс `(ticker, timestamp)`;
повторный запуск допустим. Изменения существующих таблиц требуют миграций.
Цена хранится как PostgreSQL NUMERIC и передаётся в репозиторий как `Decimal`.
`timestamp` — UNIX timestamp в секундах.

`PriceRepository` принимает `AsyncSession`. Запись выполняет `flush`,
а commit/rollback принадлежит вызывающему коду. Для API используйте
`get_session` через `Depends`: успешный запрос фиксирует транзакцию,
исключение откатывает её, сессия закрывается. Для фонового кода:

```python
from decimal import Decimal
from app.db.session import SessionFactory
from app.repositories.price_repository import PriceRepository

async with SessionFactory.begin() as session:
    await PriceRepository(session).create_price(
        "BTC_USD", Decimal("65000.12"), 1800000000
    )
```

История упорядочена по `(timestamp, id)`, последняя цена — по максимальным
`timestamp` и `id`. Временной диапазон включает обе границы;
обратный диапазон вызывает `ValueError`.

## Интеграционные тесты

Создайте отдельную тестовую базу PostgreSQL и задайте её URL:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/deribit_test python -m pytest -q
```

Тесты работают с настоящим PostgreSQL и откатывают изменения после каждого
теста. Без `TEST_DATABASE_URL` они пропускаются.

## Клиент Deribit

`DeribitClient` работает независимо от FastAPI и Celery. Он вызывает публичный
метод `GET /public/get_index_price` относительно `DERIBIT_BASE_URL`:
[документация Deribit](https://test.deribit.com/api_console/?method=%2Fpublic%2Fget_index_price).
API-ключ не требуется. Пример запуска из Python:

```python
import asyncio
import aiohttp
from app.clients.deribit_client import DeribitClient

async def main():
    async with aiohttp.ClientSession() as session:
        client = DeribitClient(session=session, timeout=10)
        btc = await client.get_index_price("btc_usd")
        eth = await client.get_index_price("eth_usd")
        print(btc, eth)

asyncio.run(main())
```

Без переданной сессии клиент создаёт и закрывает сессию на каждый вызов.
Переданной сессией управляет вызывающий код. Тайм-аут по умолчанию — 10 секунд.
Метод возвращает положительный конечный `float`, как предусмотрено интерфейсом.
При передаче цены в репозиторий используйте `Decimal(str(price))`.

Ошибки наследуются от `DeribitClientError`: `DeribitTimeoutError` для тайм-аута,
`DeribitHTTPError` для HTTP-ошибок (с атрибутом `status`), `DeribitRPCError`
для JSON-RPC-ошибок (с атрибутом `error`), `DeribitResponseError` для неверного
JSON, структуры ответа или цены. Ошибки соединения дают `DeribitClientError`.

Тесты клиента выполняются без сети и базы данных:

```bash
python -m pytest -q tests/test_deribit_client.py
```

## Сервисы и ручной сбор

`PriceService(repository)` проверяет тикеры `BTC_USD` и `ETH_USD` до обращения
к репозиторию. `get_all_prices` и `get_filtered_prices` возвращают пустой список,
если записей нет; `get_latest_price` вызывает `PriceNotFoundError`.
Неподдерживаемый тикер вызывает `InvalidTickerError`. Границы фильтра —
неотрицательные целые UNIX секунды, включая обе границы; неверный диапазон
вызывает `InvalidTimeRangeError`.

`CollectorService(client, repository).collect_prices()` последовательно получает
оба индекса, преобразует цену через `Decimal(str(price))` и сохраняет время
получения в UNIX секундах. Ошибка API для одного индекса логируется и не мешает
второму. Если недоступны оба индекса, вызывается `PriceCollectionError`.
Ошибки БД передаются вызывающему коду для отката транзакции.
Сервис не выполняет commit: этим управляет вызывающий код.

Для ручного сбора сначала настройте PostgreSQL и `.env`, затем выполните:

```bash
python -m scripts.init_db
python -m scripts.collect_prices
```

Скрипт управляет HTTP-сессией и транзакцией БД, фиксирует полученные записи
и освобождает ресурсы. Если получена только одна цена, она будет сохранена.
При сбое БД вся транзакция откатывается. Логи используют `LOG_LEVEL` из настроек.

Тесты сервисов не требуют подключения к API или БД:

```bash
python -m pytest -q tests/test_price_service.py tests/test_collector_service.py
```

## CI

GitHub Actions (`.github/workflows/ci.yml`) запускается при push, pull request
и вручную через вкладку Actions. Проверки выполняются на Python 3.11 и 3.12:
установка зависимостей, `pip check`, двукратная инициализация таблиц и весь набор
тестов, включая интеграционные тесты с PostgreSQL 16.

PostgreSQL запускается отдельным сервисом с проверкой готовности, а
`DATABASE_URL` и `TEST_DATABASE_URL` заданы в workflow. Секреты и `.env`
для CI не нужны. Запросы Deribit замокированы в тестах.
Настройка сервисного контейнера следует
[документации GitHub Actions](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers).
