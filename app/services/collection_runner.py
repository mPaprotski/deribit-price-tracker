import asyncio
import logging

import aiohttp
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.clients.deribit_client import DeribitClient
from app.core.config import get_settings
from app.repositories.price_repository import PriceRepository
from app.services.collector_service import CollectorService

logger = logging.getLogger(__name__)


async def run_collection() -> None:
    """Own all asynchronous resources within the current event loop."""
    engine = create_async_engine(get_settings().DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with asyncio.timeout(45):
            async with aiohttp.ClientSession() as http_session:
                async with factory.begin() as session:
                    await CollectorService(
                        DeribitClient(session=http_session), PriceRepository(session)
                    ).collect_prices()
                logger.info("Price collection transaction committed")
    finally:
        await engine.dispose()
