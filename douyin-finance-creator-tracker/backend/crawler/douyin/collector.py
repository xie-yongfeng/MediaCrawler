from __future__ import annotations

import asyncio
import sys

from .client import DouyinApiClient
from .errors import DataFetchError
from .models import CollectResult
from .parser import parse_aweme, parse_creator
from .session import DouyinSession


class DouyinCollector:
    """Collect target creator data through signed, active Douyin web requests."""

    def __init__(self, cdp_url: str = "http://127.0.0.1:9222") -> None:
        self.session = DouyinSession(cdp_url)
        self._loop: asyncio.AbstractEventLoop | None = None

    def _create_loop(self) -> asyncio.AbstractEventLoop:
        if sys.platform == "win32":
            return asyncio.WindowsProactorEventLoopPolicy().new_event_loop()
        return asyncio.new_event_loop()

    def _run(self, coroutine):
        if self._loop is None:
            raise RuntimeError("采集器尚未启动。")
        return self._loop.run_until_complete(coroutine)

    def start(self) -> None:
        if self._loop is not None:
            return
        self._loop = self._create_loop()
        try:
            asyncio.set_event_loop(self._loop)
            self._run(self.session.start())
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self._loop is None:
            return
        loop = self._loop
        self._loop = None
        try:
            loop.run_until_complete(self.session.close())
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    def fetch_creator(self, sec_user_id: str, since: int, limit: int = 15) -> CollectResult:
        return self._run(self._fetch_creator(sec_user_id, since, limit))

    async def _fetch_creator(self, sec_user_id: str, since: int, limit: int) -> CollectResult:
        page = self.session.active_page()
        client = DouyinApiClient(page)
        creator_payload = await client.get_creator(sec_user_id)
        creator = parse_creator(sec_user_id, creator_payload)
        if creator.sec_user_id != sec_user_id:
            raise DataFetchError("资料响应的账号与目标博主不一致，已拒绝导入以防止内容错归属。")
        if not creator.nickname:
            raise DataFetchError("创作者资料响应缺少昵称，已停止导入。")

        raw_awemes, reached_cursor = await client.get_creator_awemes(sec_user_id, since, limit)
        awemes = []
        for raw_aweme in raw_awemes:
            aweme = parse_aweme(raw_aweme)
            if aweme:
                awemes.append(aweme)
        return CollectResult(creator, awemes, reached_cursor)
