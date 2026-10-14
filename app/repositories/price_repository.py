from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PriceRecord


class PriceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_price(self, ticker: str, price: Decimal, timestamp: int) -> PriceRecord:
        """Insert a record; the caller owns commit/rollback."""
        record = PriceRecord(ticker=ticker, price=price, timestamp=timestamp)
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_all_by_ticker(self, ticker: str) -> list[PriceRecord]:
        statement = (
            select(PriceRecord)
            .where(PriceRecord.ticker == ticker)
            .order_by(PriceRecord.timestamp, PriceRecord.id)
        )
        return list((await self.session.scalars(statement)).all())

    async def get_latest_by_ticker(self, ticker: str) -> PriceRecord | None:
        statement = (
            select(PriceRecord)
            .where(PriceRecord.ticker == ticker)
            .order_by(PriceRecord.timestamp.desc(), PriceRecord.id.desc())
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def get_by_time_range(
        self, ticker: str, start_timestamp: int, end_timestamp: int
    ) -> list[PriceRecord]:
        """Return records within the inclusive UNIX timestamp range."""
        if start_timestamp > end_timestamp:
            raise ValueError("start_timestamp must not exceed end_timestamp")
        statement = (
            select(PriceRecord)
            .where(
                PriceRecord.ticker == ticker,
                PriceRecord.timestamp.between(start_timestamp, end_timestamp),
            )
            .order_by(PriceRecord.timestamp, PriceRecord.id)
        )
        return list((await self.session.scalars(statement)).all())
