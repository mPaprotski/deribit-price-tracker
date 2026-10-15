import asyncio
import math

import aiohttp

from app.core.config import get_settings


class DeribitClientError(Exception):
    """Base error for failures while retrieving an index price."""


class DeribitTimeoutError(DeribitClientError):
    pass


class DeribitHTTPError(DeribitClientError):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f"Deribit returned HTTP {status}")


class DeribitResponseError(DeribitClientError):
    pass


class DeribitRPCError(DeribitClientError):
    def __init__(self, error: object):
        self.error = error
        super().__init__(f"Deribit JSON-RPC error: {error}")


class DeribitClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 10.0,
        session: aiohttp.ClientSession | None = None,
    ):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        self.base_url = (base_url or get_settings().DERIBIT_BASE_URL).rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session = session

    async def get_index_price(self, index_name: str) -> float:
        """Fetch an index price; an injected HTTP session remains caller-owned."""
        if not index_name or not index_name.strip():
            raise ValueError("index_name must not be empty")
        if self._session is not None:
            return await self._get_index_price(self._session, index_name)
        async with aiohttp.ClientSession() as session:
            return await self._get_index_price(session, index_name)

    async def _get_index_price(
        self, session: aiohttp.ClientSession, index_name: str
    ) -> float:
        try:
            async with session.get(
                f"{self.base_url}/public/get_index_price",
                params={"index_name": index_name},
                timeout=self.timeout,
            ) as response:
                if response.status >= 400:
                    raise DeribitHTTPError(response.status)
                try:
                    payload = await response.json()
                except (ValueError, aiohttp.ContentTypeError) as exc:
                    raise DeribitResponseError("Deribit returned invalid JSON") from exc
        except asyncio.TimeoutError as exc:
            raise DeribitTimeoutError("Deribit request timed out") from exc
        except aiohttp.ClientError as exc:
            raise DeribitClientError("Unable to request the Deribit API") from exc

        if not isinstance(payload, dict):
            raise DeribitResponseError("Deribit response must be a JSON object")
        if "error" in payload:
            raise DeribitRPCError(payload["error"])
        result = payload.get("result")
        if not isinstance(result, dict) or "index_price" not in result:
            raise DeribitResponseError("Deribit response is missing result.index_price")
        value = result["index_price"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise DeribitResponseError("Index price must be a number")
        try:
            price = float(value)
        except (OverflowError, ValueError) as exc:
            raise DeribitResponseError("Index price must be positive and finite") from exc
        if not math.isfinite(price) or price <= 0:
            raise DeribitResponseError("Index price must be positive and finite")
        return price
