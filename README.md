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
