import logging
from time import time
from decimal import Decimal

from app.clients.deribit_client import DeribitClient, DeribitClientError
from app.core.constants import SUPPORTED_TICKERS
from app.repositories.price_repository import PriceRepository

logger = logging.getLogger(__name__)


class PriceCollectionError(Exception):
    """No supported index could be retrieved during a collection run."""


class CollectorService:
    def __init__(self, client: DeribitClient, repository: PriceRepository):
        self.client = client
        self.repository = repository

    async def collect_prices(self) -> None:
        """Collect each index independently; the caller owns the transaction."""
        collected = 0
        for ticker in SUPPORTED_TICKERS:
            try:
                price = await self.client.get_index_price(ticker.lower())
            except DeribitClientError:
                logger.exception("Failed to retrieve price for %s", ticker)
                continue
            timestamp = int(time())
            # str avoids introducing additional binary float artifacts into Decimal.
            await self.repository.create_price(ticker, Decimal(str(price)), timestamp)
            collected += 1
            logger.info("Price staged: ticker=%s price=%s timestamp=%s", ticker, price, timestamp)
        if collected == 0:
            raise PriceCollectionError("Failed to retrieve prices for all supported tickers")
