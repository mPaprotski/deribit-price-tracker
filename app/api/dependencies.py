from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.repositories.price_repository import PriceRepository
from app.services.price_service import PriceService


async def get_db(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AsyncIterator[AsyncSession]:
    yield session


async def get_price_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PriceService:
    return PriceService(PriceRepository(session))
