from app.core.constants import SUPPORTED_TICKERS
from app.db.models import PriceRecord
from app.repositories.price_repository import PriceRepository


class InvalidTickerError(ValueError):
    pass


class InvalidTimeRangeError(ValueError):
    pass


class PriceNotFoundError(LookupError):
    pass


class PriceService:
    def __init__(self, repository: PriceRepository):
        self.repository = repository

    @staticmethod
    def _validate_ticker(ticker: str) -> None:
        if ticker not in SUPPORTED_TICKERS:
            raise InvalidTickerError(f"Unsupported ticker: {ticker!r}")

    async def get_all_prices(self, ticker: str) -> list[PriceRecord]:
        self._validate_ticker(ticker)
        return await self.repository.get_all_by_ticker(ticker)

    async def get_latest_price(self, ticker: str) -> PriceRecord:
        self._validate_ticker(ticker)
        record = await self.repository.get_latest_by_ticker(ticker)
        if record is None:
            raise PriceNotFoundError(f"No price found for {ticker}")
        return record

    async def get_filtered_prices(
        self, ticker: str, start_timestamp: int, end_timestamp: int
    ) -> list[PriceRecord]:
        self._validate_ticker(ticker)
        for value in (start_timestamp, end_timestamp):
            if type(value) is not int or value < 0:
                raise InvalidTimeRangeError("Timestamps must be non-negative integer UNIX seconds")
        if start_timestamp > end_timestamp:
            raise InvalidTimeRangeError("start_timestamp must not exceed end_timestamp")
        return await self.repository.get_by_time_range(ticker, start_timestamp, end_timestamp)
