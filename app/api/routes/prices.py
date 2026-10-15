from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_price_service
from app.schemas.price import PriceFilterParams, PriceResponse, Ticker
from app.services.price_service import PriceService

router = APIRouter(prefix="/prices", tags=["Prices"])
PriceServiceDependency = Annotated[PriceService, Depends(get_price_service)]


@router.get("", response_model=list[PriceResponse], summary="Get price history")
async def get_prices(ticker: Annotated[Ticker, Query()], service: PriceServiceDependency):
    return await service.get_all_prices(ticker)


@router.get(
    "/latest", response_model=PriceResponse, summary="Get latest price",
    responses={404: {"description": "No saved price for this ticker"}},
)
async def get_latest_price(ticker: Annotated[Ticker, Query()], service: PriceServiceDependency):
    return await service.get_latest_price(ticker)


@router.get("/filter", response_model=list[PriceResponse], summary="Get prices in an inclusive time range")
async def get_filtered_prices(
    params: Annotated[PriceFilterParams, Query()], service: PriceServiceDependency,
):
    return await service.get_filtered_prices(params.ticker, params.start_time, params.end_time)
