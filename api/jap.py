"""
api/jap.py — JustAnotherPanel API v2 client (async).
Supports test mode when no real API key is set.
Hot-reload credentials at runtime without restarting the bot.
"""

import asyncio
import logging
from typing import Optional

import aiohttp

import database as db
from config import JAP_API_KEY, JAP_BASE_URL, JAP_TIMEOUT

logger = logging.getLogger(__name__)

_TEST_SERVICES = [
    {"service": "1", "name": "Instagram Followers [Test]",
     "type": "Default", "rate": "0.50", "min": "100",  "max": "10000"},
    {"service": "2", "name": "Instagram Likes [Test]",
     "type": "Default", "rate": "0.20", "min": "50",   "max": "5000"},
    {"service": "3", "name": "Instagram Views [Test]",
     "type": "Default", "rate": "0.10", "min": "100",  "max": "50000"},
    {"service": "4", "name": "Instagram Comments [Test]",
     "type": "Default", "rate": "1.00", "min": "10",   "max": "500"},
]

_TEST_KEYS = {"TEST_API_KEY_12345", "YOUR_JAP_API_KEY_HERE", ""}


class JAPClient:
    def __init__(self) -> None:
        self.api_key  = JAP_API_KEY
        self.base_url = JAP_BASE_URL

    # ─── Live credentials from DB ──────────────────────────────────────────
    async def _refresh_credentials(self) -> None:
        """Pull the latest key + URL from DB before every real request."""
        key = await db.get_setting("jap_api_key", "")
        url = await db.get_setting("jap_api_url", "") or JAP_BASE_URL
        if key:
            self.api_key  = key
        if url:
            self.base_url = url

    @property
    def is_test_mode(self) -> bool:
        return self.api_key in _TEST_KEYS

    # ─── Internal POST ─────────────────────────────────────────────────────
    async def _post(self, payload: dict) -> Optional[dict | list]:
        await self._refresh_credentials()
        payload["key"] = self.api_key
        timeout = aiohttp.ClientTimeout(total=JAP_TIMEOUT)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as sess:
                async with sess.post(self.base_url, data=payload) as resp:
                    if resp.status == 200:
                        return await resp.json(content_type=None)
                    logger.error(f"JAP HTTP {resp.status}")
                    return None
        except asyncio.TimeoutError:
            logger.error("JAP request timed out")
            return None
        except Exception as ex:
            logger.error(f"JAP request error: {ex}")
            return None

    # ─── Public API ────────────────────────────────────────────────────────
    async def place_order(
        self,
        service_id: str,
        link: str,
        quantity: int,
    ) -> Optional[str]:
        """
        Place a new order.
        Returns JAP order ID string, or None on failure.
        In test mode returns a fake order ID immediately.
        """
        if self.is_test_mode:
            return f"TEST_{abs(hash(link + str(quantity))) % 999999:06d}"

        result = await self._post({
            "action":   "add",
            "service":  service_id,
            "link":     link,
            "quantity": str(quantity),
        })
        if result and "order" in result:
            return str(result["order"])
        logger.error(f"JAP place_order failed: {result}")
        return None

    async def check_status(self, order_id: str) -> Optional[dict]:
        """
        Check order status.
        Returns dict with 'status', 'remains', etc., or None.
        """
        if self.is_test_mode or (order_id or "").startswith("TEST_"):
            return {"status": "In progress", "remains": "—", "start_count": 0}

        result = await self._post({"action": "status", "order": order_id})
        if result and "status" in result:
            return result
        return None

    async def get_balance(self) -> Optional[str]:
        if self.is_test_mode:
            return "100.00"
        result = await self._post({"action": "balance"})
        if result and "balance" in result:
            return str(result["balance"])
        return None

    async def get_services(self) -> Optional[list]:
        if self.is_test_mode:
            return _TEST_SERVICES
        result = await self._post({"action": "services"})
        if isinstance(result, list):
            return result
        return None

    async def get_service_price(self, service_id: str) -> Optional[str]:
        services = await self.get_services()
        if not services:
            return None
        for svc in services:
            if str(svc.get("service", "")) == str(service_id):
                rate = svc.get("rate", "")
                return f"${rate}" if rate else None
        return None

    def reload(self, api_key: str = "", base_url: str = "") -> None:
        """Hot-reload credentials without restarting the bot."""
        if api_key:
            self.api_key  = api_key
        if base_url:
            self.base_url = base_url


# Singleton
jap = JAPClient()
