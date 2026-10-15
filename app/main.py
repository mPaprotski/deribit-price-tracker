from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes.prices import router as prices_router
from app.services.price_service import InvalidTickerError, InvalidTimeRangeError, PriceNotFoundError

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = get_settings()
    configure_logging(app.state.settings.LOG_LEVEL)
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(
    title="Deribit Price Tracker",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(prices_router)


@app.exception_handler(PriceNotFoundError)
async def price_not_found_handler(request: Request, exc: PriceNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InvalidTickerError)
@app.exception_handler(InvalidTimeRangeError)
async def invalid_price_request_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})
