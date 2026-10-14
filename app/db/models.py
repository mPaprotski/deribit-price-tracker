from decimal import Decimal

from sqlalchemy import BigInteger, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PriceRecord(Base):
    __tablename__ = "price_records"
    __table_args__ = (Index("ix_price_records_ticker_timestamp", "ticker", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    timestamp: Mapped[int] = mapped_column(BigInteger, nullable=False)
