import asyncio
import os
from pathlib import Path
import shutil
from typing import Optional
from playwright.async_api import Page, Download

from app.flow.base import FlowDownloadError
from app.flow.selectors import (
    DOWNLOAD_BUTTON_SELECTORS,
    GENERATED_VIDEO_SELECTORS,
    MORE_OPTIONS_SELECTORS,
)
from app.merger.ffmpeg import probe_media
from app.utils.logger import logger


def validate_downloaded_clip(file_path: str) -> bool:
    """Verifies that the downloaded video file exists, is non-empty, and has a valid container header."""
    if not os.path.isfile(file_path):
        return False
    if os.path.getsize(file_path) < 1024:
        return False

    # Check MP4 file signature (ftyp)
    try:
        with open(file_path, "rb") as f:
            header = f.read(16)
            if b"ftyp" in header or b"moov" in header or b"mdat" in header:
                return True
    except Exception:
        pass

    # Fallback to ffprobe validation
    try:
        probe = probe_media(file_path)
        return probe.get("duration", 0) > 0 and probe["video"]["codec"] is not None
    except Exception:
        return False


async def trigger_download(page: Page, target_path: str, timeout: float = 120.0) -> str:
    """
    Triggers the download of the finished video clip from the Google Flow canvas,
    waits for the browser download stream to complete, and moves it to target_path.
    """
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target.with_suffix(".downloading.mp4")

    logger.info(f"Initiating download for clip -> {target.name}...")

    # Look for download button directly
    download_btn = None
    for btn_sel in DOWNLOAD_BUTTON_SELECTORS:
        try:
            el = await page.query_selector(btn_sel)
            if el and await el.is_visible():
                download_btn = el
                break
        except Exception:
            pass

    # If not directly visible, hover over latest video card or click more options
    if not download_btn:
        for vid_sel in GENERATED_VIDEO_SELECTORS:
            try:
                vid_el = await page.query_selector(vid_sel)
                if vid_el and await vid_el.is_visible():
                    await vid_el.hover()
                    await asyncio.sleep(0.5)
                    # Check again for download button
                    for btn_sel in DOWNLOAD_BUTTON_SELECTORS:
                        el = await page.query_selector(btn_sel)
                        if el and await el.is_visible():
                            download_btn = el
                            break
                    if download_btn:
                        break
            except Exception:
                pass

    # If still not found, try more options menu (three dots)
    if not download_btn:
        for menu_sel in MORE_OPTIONS_SELECTORS:
            try:
                menu_btn = await page.query_selector(menu_sel)
                if menu_btn and await menu_btn.is_visible():
                    await menu_btn.click()
                    await asyncio.sleep(0.5)
                    for btn_sel in DOWNLOAD_BUTTON_SELECTORS:
                        el = await page.query_selector(btn_sel)
                        if el and await el.is_visible():
                            download_btn = el
                            break
                    if download_btn:
                        break
            except Exception:
                pass

    if download_btn:
        try:
            async with page.expect_download(timeout=timeout * 1000) as download_info:
                await download_btn.click()
            download: Download = await download_info.value
            await download.save_as(str(temp_target))
        except Exception as e:
            raise FlowDownloadError(f"Download trigger failed or timed out: {e}")
    else:
        # Fallback: check if video element has a direct downloadable src
        video_src = None
        for vid_sel in GENERATED_VIDEO_SELECTORS:
            try:
                el = await page.query_selector(vid_sel)
                if el:
                    src = await el.get_attribute("src")
                    if src and src.startswith("http"):
                        video_src = src
                        break
            except Exception:
                pass

        if video_src:
            logger.info("Direct video URL found; streaming video content...")
            try:
                response = await page.request.get(video_src, timeout=timeout * 1000)
                if response.status != 200:
                    raise FlowDownloadError(f"Direct stream download returned HTTP {response.status}")
                body = await response.body()
                with open(temp_target, "wb") as f:
                    f.write(body)
            except Exception as e:
                raise FlowDownloadError(f"Failed to fetch video stream: {e}")
        else:
            raise FlowDownloadError("Could not locate a download button or media source in Google Flow.")

    # Move from temporary to destination target
    if temp_target.exists():
        if target.exists():
            target.unlink()
        shutil.move(str(temp_target), str(target))

    # Validate downloaded file
    if not validate_downloaded_clip(str(target)):
        raise FlowDownloadError(f"Downloaded video file validation failed: {target}")

    file_size_kb = os.path.getsize(str(target)) // 1024
    logger.info(f"Download completed successfully: {target.name} ({file_size_kb} KB)")
    return str(target)
