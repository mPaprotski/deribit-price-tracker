from decimal import Decimal

import pytest
from sqlalchemy import inspect

from app.repositories.price_repository import PriceRepository


async def test_create_and_read_decimal(session):
    repository = PriceRepository(session)
    price = Decimal("12345.123456789012345678")
    record = await repository.create_price("BTC_USD", price, 1_800_000_000)
    assert record.id is not None
    session.expire_all()
    saved = await repository.get_latest_by_ticker("BTC_USD")
    assert saved.price == price
    assert saved.timestamp == 1_800_000_000


async def test_history_order_and_ticker_filter(session):
    repository = PriceRepository(session)
    for ticker, timestamp in [("BTC_USD", 30), ("ETH_USD", 20), ("BTC_USD", 10)]:
        await repository.create_price(ticker, Decimal("100"), timestamp)
    records = await repository.get_all_by_ticker("BTC_USD")
    assert [record.timestamp for record in records] == [10, 30]
    assert await repository.get_all_by_ticker("UNKNOWN") == []


async def test_latest_uses_timestamp_then_id(session):
    repository = PriceRepository(session)
    first = await repository.create_price("BTC_USD", Decimal("100"), 30)
    await repository.create_price("BTC_USD", Decimal("200"), 10)
    last = await repository.create_price("BTC_USD", Decimal("300"), 30)
    await repository.create_price("ETH_USD", Decimal("400"), 40)
    latest = await repository.get_latest_by_ticker("BTC_USD")
    assert latest.id == last.id
    assert latest.id != first.id
    assert await repository.get_latest_by_ticker("UNKNOWN") is None


async def test_time_range_includes_boundaries(session):
    repository = PriceRepository(session)
    for timestamp in [9, 10, 15, 20, 21]:
        await repository.create_price("BTC_USD", Decimal("100"), timestamp)
    await repository.create_price("ETH_USD", Decimal("100"), 15)
    records = await repository.get_by_time_range("BTC_USD", 10, 20)
    assert [record.timestamp for record in records] == [10, 15, 20]
    assert await repository.get_by_time_range("BTC_USD", 30, 40) == []
    with pytest.raises(ValueError):
        await repository.get_by_time_range("BTC_USD", 20, 10)


async def test_insert_rollback(session):
    repository = PriceRepository(session)
    with pytest.raises(RuntimeError):
        async with session.begin_nested():
            await repository.create_price("BTC_USD", Decimal("100"), 10)
            raise RuntimeError("Abort transaction")
    assert await repository.get_all_by_ticker("BTC_USD") == []


async def test_composite_index(session):
    connection = await session.connection()
    indexes = await connection.run_sync(lambda conn: inspect(conn).get_indexes("price_records"))
    assert any(index["column_names"] == ["ticker", "timestamp"] for index in indexes)


async def test_commit_visible_to_new_session(session):
    from sqlalchemy.ext.asyncio import AsyncSession

    repository = PriceRepository(session)
    record = await repository.create_price("BTC_USD", Decimal("123.45"), 10)
    await session.commit()
    async with AsyncSession(bind=session.bind) as reader:
        saved = await PriceRepository(reader).get_latest_by_ticker("BTC_USD")
        assert saved.id == record.id
        assert saved.price == Decimal("123.45")
