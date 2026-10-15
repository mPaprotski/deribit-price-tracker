import asyncio
import logging
from decimal import Decimal
from unittest.mock import AsyncMock, call, patch

import pytest

from app.clients.deribit_client import DeribitClient, DeribitClientError
from app.repositories.price_repository import PriceRepository
from app.services.collector_service import CollectorService, PriceCollectionError


@pytest.fixture
def dependencies():
    return AsyncMock(spec=DeribitClient), AsyncMock(spec=PriceRepository)


async def test_collects_both_prices(dependencies, caplog):
    client, repository = dependencies
    client.get_index_price.side_effect = [65000.12, 3000.34]
    with patch("app.services.collector_service.time", side_effect=[1800000000.9, 1800000001.1]), caplog.at_level(logging.INFO):
        assert await CollectorService(client, repository).collect_prices() is None
    assert client.get_index_price.await_args_list == [call("btc_usd"), call("eth_usd")]
    assert repository.create_price.await_args_list == [
        call("BTC_USD", Decimal("65000.12"), 1800000000),
        call("ETH_USD", Decimal("3000.34"), 1800000001),
    ]
    assert "BTC_USD" in caplog.text and "ETH_USD" in caplog.text


@pytest.mark.parametrize("failed_index", [0, 1])
async def test_one_api_failure_does_not_discard_other_price(dependencies, failed_index, caplog):
    client, repository = dependencies
    responses = [65000.12, 3000.34]
    responses[failed_index] = DeribitClientError("API unavailable")
    client.get_index_price.side_effect = responses
    await CollectorService(client, repository).collect_prices()
    assert client.get_index_price.await_count == 2
    repository.create_price.assert_awaited_once()
    assert repository.create_price.await_args.args[0] == ("ETH_USD" if failed_index == 0 else "BTC_USD")
    assert "Failed to retrieve" in caplog.text


async def test_all_api_failures_reported_after_both_attempts(dependencies):
    client, repository = dependencies
    client.get_index_price.side_effect = DeribitClientError("offline")
    with pytest.raises(PriceCollectionError):
        await CollectorService(client, repository).collect_prices()
    assert client.get_index_price.await_count == 2
    repository.create_price.assert_not_awaited()


async def test_database_failure_propagates_for_transaction_rollback(dependencies):
    client, repository = dependencies
    client.get_index_price.return_value = 123.45
    repository.create_price.side_effect = RuntimeError("Database unavailable")
    with pytest.raises(RuntimeError):
        await CollectorService(client, repository).collect_prices()


async def test_cancellation_propagates(dependencies):
    client, repository = dependencies
    client.get_index_price.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await CollectorService(client, repository).collect_prices()
    repository.create_price.assert_not_awaited()
