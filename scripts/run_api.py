import argparse

import uvicorn

from app.core.config import get_settings
from app.core.logging import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the price API using environment settings")
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    uvicorn.run(
        "app.main:app", host=args.host, port=args.port,
        reload=args.reload, log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
