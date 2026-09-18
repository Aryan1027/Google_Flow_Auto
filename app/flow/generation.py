import asyncio
import time
from typing import Optional
from playwright.async_api import Page

from app.flow.base import FlowGenerationError
from app.flow.selectors import (
    ERROR_ALERT_SELECTORS,
    GENERATED_VIDEO_SELECTORS,
    GENERATING_INDICATORS,
)
from app.utils.logger import logger


async def wait_for_generation_start(page: Page, timeout: float = 30.0) -> bool:
    """
    Detects when Google Flow begins processing the submitted prompt.
    Checks for appearance of spinner, progress text, or disabled submit button.
    """
    start_time = time.monotonic()
    logger.info("Detecting generation start...")

    while (time.monotonic() - start_time) < timeout:
        # Check for error banners first
        for err_sel in ERROR_ALERT_SELECTORS:
            try:
                el = await page.query_selector(err_sel)
                if el and await el.is_visible():
                    txt = await el.inner_text()
                    raise FlowGenerationError(f"Flow returned error on submission: {txt.strip()}")
            except FlowGenerationError:
                raise
            except Exception:
                pass

        # Check for active spinner or generating indicator
        for gen_sel in GENERATING_INDICATORS:
            try:
                el = await page.query_selector(gen_sel)
                if el and await el.is_visible():
                    logger.info("Generation started indicator detected.")
                    return True
            except Exception:
                pass

        await asyncio.sleep(0.5)

    logger.warning("Generation start indicator not explicitly detected within timeout; proceeding to completion polling.")
    return False


async def poll_generation_completion(page: Page, timeout: float = 300.0, polling_interval: float = 2.0) -> str:
    """
    Polls Google Flow at sensible intervals until the video generation is complete.
    Does NOT use fixed wait times. Watches for completion elements and errors.
    """
    start_time = time.monotonic()
    logger.info(f"Monitoring generation progress (max timeout: {timeout}s)...")

    last_logged_elapsed = 0

    while (time.monotonic() - start_time) < timeout:
        elapsed = int(time.monotonic() - start_time)
        if elapsed > 0 and elapsed % 15 == 0 and elapsed != last_logged_elapsed:
            logger.info(f"Generation in progress ({elapsed}s elapsed)...")
            last_logged_elapsed = elapsed

        # Check for error alerts
        for err_sel in ERROR_ALERT_SELECTORS:
            try:
                el = await page.query_selector(err_sel)
                if el and await el.is_visible():
                    txt = await el.inner_text()
                    raise FlowGenerationError(f"Flow generation aborted with error: {txt.strip()}")
            except FlowGenerationError:
                raise
            except Exception:
                pass

        # Check for completed video element
        for vid_sel in GENERATED_VIDEO_SELECTORS:
            try:
                elements = await page.query_selector_all(vid_sel)
                for el in elements:
                    if await el.is_visible():
                        # Verify video has src or is playable
                        src = await el.get_attribute("src")
                        if src and len(src) > 5:
                            logger.info(f"Generation completed! Video element detected with src: {src[:50]}...")
                            return src
                        # Even if blob or internal, video element existence is a strong signal
                        logger.info("Generation completed! Video element visible on canvas.")
                        return vid_sel
            except Exception:
                pass

        # Check if spinner has finished and asset card is now stationary
        still_generating = False
        for gen_sel in GENERATING_INDICATORS:
            try:
                el = await page.query_selector(gen_sel)
                if el and await el.is_visible():
                    still_generating = True
                    break
            except Exception:
                pass

        if not still_generating and elapsed > 5:
            # Check once more if a video or download button is now present
            for vid_sel in GENERATED_VIDEO_SELECTORS:
                try:
                    el = await page.query_selector(vid_sel)
                    if el and await el.is_visible():
                        logger.info("Generation completed (spinner dismissed and video rendered).")
                        return vid_sel
                except Exception:
                    pass

        await asyncio.sleep(polling_interval)

    raise FlowGenerationError(f"Generation timeout after {timeout} seconds. Google Flow did not finish.")
