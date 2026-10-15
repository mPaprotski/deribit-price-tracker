from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

Ticker = Literal["BTC_USD", "ETH_USD"]
UnixTimestamp = Annotated[int, Field(ge=0, le=2**63 - 1, description="UNIX timestamp in seconds")]


class PriceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: Ticker
    price: Decimal
    timestamp: int

    @field_serializer("price", when_used="json")
    def serialize_price(self, price: Decimal) -> str:
        return format(price, "f")


class PriceFilterParams(BaseModel):
    ticker: Ticker
    start_time: UnixTimestamp
    end_time: UnixTimestamp

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.start_time > self.end_time:
            raise ValueError("start_time must not exceed end_time")
        return self
