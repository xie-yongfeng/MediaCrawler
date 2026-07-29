from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shutil
import subprocess
import sys

from playwright.async_api import Browser, BrowserContext, Page, Playwright, TimeoutError as PlaywrightTimeoutError, async_playwright

from .errors import DataFetchError, LoginExpired


class DouyinSession:
    """Use the application-owned persistent Chrome instead of launching browsers."""

    def __init__(self, cdp_url: str = "http://127.0.0.1:9222", login_timeout_seconds: int = 180) -> None:
        self.cdp_url = cdp_url
        self.login_timeout_seconds = login_timeout_seconds
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def _cdp_ready(self) -> bool:
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", 9222), timeout=0.75)
            writer.close()
            await writer.wait_closed()
            return True
        except (OSError, TimeoutError):
            return False

    @staticmethod
    def _browser_path() -> str | None:
        configured = os.environ.get("CHROME_PATH", "").strip()
        if configured and Path(configured).is_file():
            return configured
        if sys.platform == "win32":
            roots = [os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", ""), os.environ.get("LOCALAPPDATA", "")]
            for suffix in ("Google/Chrome/Application/chrome.exe", "Microsoft/Edge/Application/msedge.exe"):
                for root in roots:
                    candidate = Path(root) / suffix
                    if root and candidate.is_file():
                        return str(candidate)
            return None
        return next((shutil.which(name) for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser") if shutil.which(name)), None)

    async def ensure_cdp_browser(self) -> None:
        """Start the application-owned visible browser only when CDP is absent."""
        if await self._cdp_ready():
            return
        browser_path = self._browser_path()
        if not browser_path:
            raise LoginExpired("未找到 Chrome 或 Edge；请安装浏览器，或设置 CHROME_PATH 后重试。")
        profile_dir = Path(os.environ.get("CDP_USER_DATA_DIR", Path(__file__).resolve().parents[2] / "data" / "chrome-profile"))
        profile_dir.mkdir(parents=True, exist_ok=True)
        args = [browser_path, "--remote-debugging-port=9222", f"--user-data-dir={profile_dir}"]
        try:
            if sys.platform == "win32":
                flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                subprocess.Popen(args, creationflags=flags, close_fds=True)
            else:
                subprocess.Popen(args, start_new_session=True, close_fds=True)
        except OSError as exc:
            raise LoginExpired("无法启动用于抖音登录的 Chrome。请检查 CHROME_PATH。") from exc
        for _ in range(30):
            await asyncio.sleep(1)
            if await self._cdp_ready():
                return
        raise LoginExpired("Chrome 已尝试启动，但 30 秒内未开放 CDP 端口 9222。请关闭占用同一用户目录的浏览器后重试。")

    @staticmethod
    async def _is_authenticated(context: BrowserContext, page: Page) -> bool:
        cookies = {cookie["name"]: cookie["value"] for cookie in await context.cookies("https://www.douyin.com")}
        if cookies.get("LOGIN_STATUS") == "1":
            return True
        if any(cookies.get(name) for name in ("sessionid", "sessionid_ss", "sid_guard", "passport_auth_status")):
            return True
        try:
            return await page.evaluate("() => window.localStorage.getItem('HasUserLogin') === '1'")
        except Exception:
            return False

    async def _open_login_panel(self, page: Page) -> None:
        """Make the QR login UI visible without bypassing any platform control."""
        await page.bring_to_front()
        for selector in (
            "[data-e2e='login-button']",
            "button:has-text('登录')",
            "p:has-text('登录')",
            "text=登录",
        ):
            try:
                await page.locator(selector).first.click(timeout=2_000)
                return
            except PlaywrightTimeoutError:
                continue
        # Some page variants display the QR panel automatically. Keep the page
        # focused so the user can still scan it rather than failing prematurely.

    async def ensure_login(self, context: BrowserContext, page: Page) -> None:
        await page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(1_000)
        if await self._is_authenticated(context, page):
            return

        await self._open_login_panel(page)
        for _ in range(self.login_timeout_seconds):
            await asyncio.sleep(1)
            if await self._is_authenticated(context, page):
                await page.wait_for_timeout(1_500)
                return
        raise LoginExpired("抖音尚未登录：已在长期 Chrome 中打开登录页，请扫码后重新同步。")

    async def start(self) -> Page:
        if self._page and not self._page.is_closed():
            return self._page
        await self.ensure_cdp_browser()
        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(self.cdp_url)
            self._context = self._browser.contexts[0] if self._browser.contexts else None
            if self._context is None:
                raise DataFetchError("长期 Chrome 未提供可用浏览器上下文。")
            self._page = await self._context.new_page()
            await self.ensure_login(self._context, self._page)
            return self._page
        except Exception as exc:
            await self.close()
            if isinstance(exc, (DataFetchError, LoginExpired)):
                raise
            raise LoginExpired("无法连接长期 Chrome；请检查浏览器是否能访问 CDP 端口 9222。") from exc

    def active_page(self) -> Page:
        if not self._page or self._page.is_closed():
            raise DataFetchError("采集会话尚未启动或已关闭。")
        return self._page

    async def close(self) -> None:
        page, browser, playwright = self._page, self._browser, self._playwright
        self._page = None
        self._browser = None
        self._context = None
        self._playwright = None
        if page and not page.is_closed():
            await page.close()
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()
