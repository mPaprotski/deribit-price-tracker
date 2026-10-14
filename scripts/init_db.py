import asyncio

from app.db.base import Base
from app.db import models  # noqa: F401: register tables before create_all
from app.db.session import engine


async def init_db() -> None:
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_db())
