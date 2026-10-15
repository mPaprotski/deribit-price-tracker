from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.collection_runner import run_collection


@pytest.mark.parametrize("failure", [False, True])
async def test_runner_owns_resources_and_transaction(failure):
    with patch("app.services.collection_runner.create_async_engine") as create_engine, patch(
        "app.services.collection_runner.async_sessionmaker"
    ) as factory, patch("app.services.collection_runner.aiohttp.ClientSession") as http, patch(
        "app.services.collection_runner.CollectorService"
    ) as collector:
        engine = create_engine.return_value
        engine.dispose = AsyncMock()
        transaction = factory.return_value.begin.return_value
        transaction.__aenter__ = AsyncMock(return_value=MagicMock())
        transaction.__aexit__ = AsyncMock(return_value=False)
        http.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        http.return_value.__aexit__ = AsyncMock(return_value=False)
        collect = AsyncMock()
        collector.return_value.collect_prices = collect
        if failure:
            collect.side_effect = RuntimeError("failure")
            with pytest.raises(RuntimeError):
                await run_collection()
            assert transaction.__aexit__.await_args.args[0] is RuntimeError
        else:
            await run_collection()
            assert transaction.__aexit__.await_args.args[0] is None
        collect.assert_awaited_once()
        engine.dispose.assert_awaited_once()
        transaction.__aexit__.assert_awaited_once()
        http.return_value.__aexit__.assert_awaited_once()
