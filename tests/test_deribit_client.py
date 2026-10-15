import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from app.clients.deribit_client import (
    DeribitClient,
    DeribitClientError,
    DeribitHTTPError,
    DeribitResponseError,
    DeribitRPCError,
    DeribitTimeoutError,
)


@pytest.fixture
def http_session():
    response = MagicMock()
    response.status = 200
    response.json = AsyncMock(return_value={"result": {"index_price": 65000.25}})
    request = MagicMock()
    request.__aenter__ = AsyncMock(return_value=response)
    request.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock(spec=aiohttp.ClientSession)
    session.get.return_value = request
    return session, request, response


@pytest.mark.parametrize("index_name, value", [("btc_usd", 65000.25), ("eth_usd", 3000)])
async def test_success(http_session, index_name, value):
    session, request, response = http_session
    response.json.return_value = {"result": {"index_price": value}}
    client = DeribitClient(base_url="https://example.com/api/v2/", session=session)
    price = await client.get_index_price(index_name)
    assert price == float(value)
    assert isinstance(price, float)
    session.get.assert_called_once_with(
        "https://example.com/api/v2/public/get_index_price",
        params={"index_name": index_name}, timeout=client.timeout,
    )
    assert client.timeout.total == 10
    request.__aexit__.assert_awaited_once()
    session.close.assert_not_called()


async def test_timeout(http_session):
    session, request, _ = http_session
    request.__aenter__.side_effect = asyncio.TimeoutError
    with pytest.raises(DeribitTimeoutError):
        await DeribitClient(session=session).get_index_price("btc_usd")


async def test_connection_failure(http_session):
    session, request, _ = http_session
    request.__aenter__.side_effect = aiohttp.ClientConnectionError("offline")
    with pytest.raises(DeribitClientError, match="Unable to request"):
        await DeribitClient(session=session).get_index_price("btc_usd")


async def test_http_500(http_session):
    session, _, response = http_session
    response.status = 500
    with pytest.raises(DeribitHTTPError) as caught:
        await DeribitClient(session=session).get_index_price("btc_usd")
    assert caught.value.status == 500
    response.json.assert_not_awaited()


@pytest.mark.parametrize("error", [ValueError("invalid JSON"), aiohttp.ContentTypeError(MagicMock(), ())])
async def test_invalid_json(http_session, error):
    session, request, response = http_session
    response.json.side_effect = error
    with pytest.raises(DeribitResponseError, match="invalid JSON"):
        await DeribitClient(session=session).get_index_price("btc_usd")
    request.__aexit__.assert_awaited_once()


async def test_json_rpc_error(http_session):
    session, _, response = http_session
    error = {"code": -32602, "message": "Invalid params"}
    response.json.return_value = {"error": error}
    with pytest.raises(DeribitRPCError) as caught:
        await DeribitClient(session=session).get_index_price("btc_usd")
    assert caught.value.error == error


@pytest.mark.parametrize("payload", [None, [], "text", {}, {"result": None}, {"result": []}, {"result": {}}])
async def test_invalid_structure_or_missing_price(http_session, payload):
    session, _, response = http_session
    response.json.return_value = payload
    with pytest.raises(DeribitResponseError):
        await DeribitClient(session=session).get_index_price("btc_usd")


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("-inf"), float("nan"), True, None, "100", [], {}, 10**400])
async def test_invalid_price(http_session, value):
    session, _, response = http_session
    response.json.return_value = {"result": {"index_price": value}}
    with pytest.raises(DeribitResponseError):
        await DeribitClient(session=session).get_index_price("btc_usd")


async def test_timeout_while_reading_body(http_session):
    session, _, response = http_session
    response.json.side_effect = asyncio.TimeoutError
    with pytest.raises(DeribitTimeoutError):
        await DeribitClient(session=session).get_index_price("btc_usd")


@pytest.mark.parametrize("failure", [False, True])
async def test_owned_session_closed(http_session, failure):
    session, _, response = http_session
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    if failure:
        response.status = 500
    with patch("app.clients.deribit_client.aiohttp.ClientSession", return_value=context):
        client = DeribitClient()
        if failure:
            with pytest.raises(DeribitHTTPError):
                await client.get_index_price("btc_usd")
        else:
            assert await client.get_index_price("btc_usd") == 65000.25
    context.__aexit__.assert_awaited_once()


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_timeout(timeout):
    with pytest.raises(ValueError):
        DeribitClient(timeout=timeout)


async def test_empty_index_rejected_before_request(http_session):
    session, _, _ = http_session
    with pytest.raises(ValueError):
        await DeribitClient(session=session).get_index_price(" ")
    session.get.assert_not_called()
