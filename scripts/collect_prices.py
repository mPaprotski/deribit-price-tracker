import asyncio
import logging

import aiohttp

from app.clients.deribit_client import DeribitClient
from app.core.config import get_settings
from app.db.session import SessionFactory, engine
from app.repositories.price_repository import PriceRepository
from app.services.collector_service import CollectorService


async def collect_prices() -> None:
    logging.basicConfig(level=get_settings().LOG_LEVEL)
    try:
        async with aiohttp.ClientSession() as http_session:
            async with SessionFactory.begin() as session:
                collector = CollectorService(
                    DeribitClient(session=http_session), PriceRepository(session)
                )
                await collector.collect_prices()
            logging.getLogger(__name__).info("Price collection transaction committed")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(collect_prices())
