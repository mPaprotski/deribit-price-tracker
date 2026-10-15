import asyncio
import logging

from app.core.config import get_settings
from app.services.collection_runner import run_collection


if __name__ == "__main__":
    logging.basicConfig(level=get_settings().LOG_LEVEL)
    asyncio.run(run_collection())
