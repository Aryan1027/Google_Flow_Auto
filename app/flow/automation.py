import asyncio
import os
from pathlib import Path
from typing import Optional
from playwright.async_api import BrowserContext, Page, async_playwright

from app.config import AppConfig
from app.flow.base import BaseFlowBot, FlowAuthenticationError, FlowGenerationError
from app.flow.download import trigger_download
from app.flow.generation import poll_generation_completion, wait_for_generation_start
from app.flow.selectors import (
    AUTH_SELECTORS,
    AUTHENTICATED_SELECTORS,
    GENERATE_BUTTON_SELECTORS,
    PROMPT_INPUT_SELECTORS,
)
from app.utils.logger import logger


class PlaywrightFlowBot(BaseFlowBot):
    """
    Playwright-based Google Flow browser automation bot.
    Designed for Windows/Linux/macOS desktop environments with persistent user profile.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.playwright = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def initialize(self) -> None:
        """Launch browser with persistent profile or connect to existing CDP session."""
        if self.page:
            return

        logger.info("Initializing Playwright browser automation...")
        self.playwright = await async_playwright().start()

        browser_cfg = self.config.browser
        if browser_cfg.cdp_endpoint:
            logger.info(f"Connecting to existing browser session via CDP: {browser_cfg.cdp_endpoint}")
            browser = await self.playwright.chromium.connect_over_cdp(browser_cfg.cdp_endpoint)
            self.context = browser.contexts[0] if browser.contexts else await browser.new_context()
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        else:
            profile_dir = Path(browser_cfg.user_data_dir).resolve()
            profile_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Launching persistent browser profile at: {profile_dir}")

            launch_kwargs = {
                "user_data_dir": str(profile_dir),
                "headless": browser_cfg.headless,
                "viewport": {"width": 1280, "height": 800},
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                ],
            }
            if browser_cfg.channel:
                launch_kwargs["channel"] = browser_cfg.channel

            try:
                self.context = await self.playwright.chromium.launch_persistent_context(**launch_kwargs)
            except Exception as e:
                logger.warning(f"Failed to launch with channel '{browser_cfg.channel}': {e}. Retrying with default chromium...")
                launch_kwargs.pop("channel", None)
                self.context = await self.playwright.chromium.launch_persistent_context(**launch_kwargs)

            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

        # Set realistic desktop user agent
        await self.context.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9",
        })

        target_url = self.config.flow.url
        logger.info(f"Navigating to Google Flow: {target_url}")
        await self.page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2.0)

    async def check_authenticated(self) -> bool:
        """Verify whether user is authenticated to Google Flow."""
        if not self.page:
            await self.initialize()

        current_url = self.page.url
        if "accounts.google.com" in current_url:
            logger.warning("Current page redirected to Google Accounts login.")
            return False

        # Check for explicit Sign-in buttons
        for sel in AUTH_SELECTORS:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    logger.warning(f"Unauthenticated indicator detected on page: {sel}")
                    return False
            except Exception:
                pass

        # Check for authenticated indicator
        for sel in AUTHENTICATED_SELECTORS:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    return True
            except Exception:
                pass

        # If neither is explicit, check if prompt input exists (implies user can create)
        for sel in PROMPT_INPUT_SELECTORS:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    return True
            except Exception:
                pass

        return True

    async def submit_prompt(self, prompt: str) -> None:
        """Type prompt into Flow prompt input and trigger generation."""
        if not self.page:
            await self.initialize()

        # Ensure authentication before submitting
        is_auth = await self.check_authenticated()
        if not is_auth:
            raise FlowAuthenticationError(
                "Google Flow authentication required. Automation paused. Please log in manually and resume."
            )

        # Locate prompt input element
        prompt_element = None
        for sel in PROMPT_INPUT_SELECTORS:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    prompt_element = el
                    break
            except Exception:
                pass

        if not prompt_element:
            raise FlowGenerationError("Could not locate prompt input box on Google Flow canvas.")

        logger.info(f"Submitting prompt: \"{prompt[:60]}...\"")
        await prompt_element.click()
        await prompt_element.fill(prompt)
        await asyncio.sleep(0.5)

        # Click Generate button
        gen_button = None
        for sel in GENERATE_BUTTON_SELECTORS:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    # Check if disabled
                    is_disabled = await el.get_attribute("disabled")
                    if not is_disabled:
                        gen_button = el
                        break
            except Exception:
                pass

        if gen_button:
            await gen_button.click()
            logger.info("Clicked Generate button.")
        else:
            # Try pressing Enter
            logger.info("Generate button not clickable; pressing Enter in prompt input.")
            await prompt_element.press("Enter")

        # Configurable delay between operations
        await asyncio.sleep(self.config.flow.delay_between_operations)

    async def wait_for_generation_started(self, timeout: float = 30.0) -> bool:
        if not self.page:
            return False
        return await wait_for_generation_start(self.page, timeout=timeout)

    async def wait_for_generation_completed(self, timeout: float = 300.0, polling_interval: float = 2.0) -> str:
        if not self.page:
            raise FlowGenerationError("Browser session not active.")
        return await poll_generation_completion(self.page, timeout=timeout, polling_interval=polling_interval)

    async def download_generated_video(self, target_path: str, timeout: float = 120.0) -> str:
        if not self.page:
            raise FlowGenerationError("Browser session not active.")
        return await trigger_download(self.page, target_path=target_path, timeout=timeout)

    async def close(self) -> None:
        """Close browser resources cleanly."""
        try:
            if self.context:
                await self.context.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.warning(f"Error during browser teardown: {e}")
        finally:
            self.context = None
            self.page = None
            self.playwright = None
            logger.info("Browser session closed.")
