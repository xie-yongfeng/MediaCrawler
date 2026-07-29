"""Active Douyin web client.

The request-signing method and bundled signing asset originate from
MediaCrawler and are subject to its NON-COMMERCIAL LEARNING LICENSE 1.1.
This file intentionally contains only the API calls required by Fund Insight
Desk; see ``vendor/NOTICE.md``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any
from urllib.parse import urlencode

import httpx
from playwright.async_api import Page

from .errors import DataFetchError, RateLimited
from .signer import sign_query

logger = logging.getLogger(__name__)


class DouyinApiClient:
    base_url = "https://www.douyin.com"

    def __init__(self, page: Page) -> None:
        self.page = page
        self._headers: dict[str, str] | None = None

    async def _prepare(self) -> None:
        if not self.page.url.startswith(self.base_url):
            await self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded", timeout=60_000)
            await self.page.wait_for_timeout(750)
        if self._headers is not None:
            return
        user_agent = await self.page.evaluate("() => navigator.userAgent")
        cookies = await self.page.context.cookies([self.base_url, "https://douyin.com"])
        cookie_header = "; ".join(f"{item['name']}={item['value']}" for item in cookies)
        self._headers = {
            "User-Agent": str(user_agent),
            "Cookie": cookie_header,
            "Host": "www.douyin.com",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
            "Accept": "application/json, text/plain, */*",
        }

    async def _common_params(self) -> dict[str, str]:
        storage = await self.page.evaluate("() => ({ msToken: window.localStorage.getItem('xmst') || '' })")
        return {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "version_code": "190600",
            "version_name": "19.6.0",
            "pc_client_type": "1",
            "cookie_enabled": "true",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Chrome",
            "platform": "PC",
            "webid": "".join(str(random.randrange(10)) for _ in range(19)),
            "msToken": str(storage.get("msToken") or ""),
        }

    async def get(self, uri: str, params: dict[str, Any]) -> dict[str, Any]:
        await self._prepare()
        assert self._headers is not None
        request_params = {**params, **(await self._common_params())}
        query = urlencode(request_params)
        request_params["a_bogus"] = sign_query(query, self._headers["User-Agent"], uri)
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.get(f"{self.base_url}{uri}", params=request_params, headers=self._headers)
        except httpx.HTTPError as exc:
            raise DataFetchError(f"抖音资料请求失败：{exc}") from exc
        if response.status_code in {403, 429}:
            raise RateLimited("抖音暂时拒绝了请求，请稍后再试。")
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise DataFetchError(f"抖音返回了非 JSON 响应（HTTP {response.status_code}）。") from exc
        if not isinstance(payload, dict):
            raise DataFetchError("抖音返回的数据结构无效。")
        status_code = payload.get("status_code")
        if status_code not in (None, 0):
            raise DataFetchError(f"抖音接口返回错误：{payload.get('status_msg') or status_code}")
        return payload

    async def get_creator(self, sec_user_id: str) -> dict[str, Any]:
        return await self.get(
            "/aweme/v1/web/user/profile/other/",
            {"sec_user_id": sec_user_id, "publish_video_strategy_type": 2, "personal_center_strategy": 1},
        )

    async def get_aweme_detail(self, aweme_id: str) -> dict[str, Any]:
        response = await self.get("/aweme/v1/web/aweme/detail/", {"aweme_id": aweme_id})
        return response.get("aweme_detail") or {}

    async def get_creator_awemes(self, sec_user_id: str, since: int, limit: int) -> tuple[list[dict[str, Any]], bool]:
        cursor = ""
        has_more = True
        reached_cursor = False
        awemes: list[dict[str, Any]] = []
        while has_more and len(awemes) < limit:
            payload = await self.get(
                "/aweme/v1/web/aweme/post/",
                {"sec_user_id": sec_user_id, "count": 18, "max_cursor": cursor, "locate_query": "false", "publish_video_strategy_type": 2},
            )
            has_more = bool(payload.get("has_more"))
            cursor = str(payload.get("max_cursor") or "")
            page_items = [item for item in payload.get("aweme_list") or [] if isinstance(item, dict)]

            def create_time_of(item: dict[str, Any]) -> int:
                try:
                    return int(item.get("create_time") or 0)
                except (TypeError, ValueError):
                    return 0

            page_items.sort(key=create_time_of, reverse=True)
            for item in page_items:
                try:
                    create_time = int(item.get("create_time") or 0)
                except (TypeError, ValueError):
                    logger.warning("Skipping aweme with an invalid create_time: aweme_id=%s", item.get("aweme_id"))
                    continue
                if create_time <= since:
                    reached_cursor = True
                    continue
                aweme_id = str(item.get("aweme_id") or "")
                if not aweme_id:
                    logger.warning("Skipping aweme without an aweme_id")
                    continue
                try:
                    detail = await self.get_aweme_detail(aweme_id)
                except Exception:
                    logger.exception("Failed to fetch aweme detail; continuing: aweme_id=%s", aweme_id)
                    await asyncio.sleep(0.25)
                    continue
                if detail and str((detail.get("author") or {}).get("sec_uid") or "") == sec_user_id:
                    awemes.append(detail)
                else:
                    logger.warning("Skipping aweme with an unverified creator: aweme_id=%s", aweme_id)
                await asyncio.sleep(0.25)
                if len(awemes) >= limit:
                    break
            if reached_cursor:
                has_more = False
            if not cursor:
                break
        return awemes, reached_cursor
