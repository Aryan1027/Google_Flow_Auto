import asyncio
import os
from pathlib import Path
import subprocess
from typing import List, Optional

from app.flow.base import BaseFlowBot, FlowAuthenticationError, FlowDownloadError, FlowGenerationError
from app.utils.logger import logger


class MockFlowBot(BaseFlowBot):
    """
    Mock implementation of Google Flow browser bot for local testing,
    environments without desktop Chrome, and CI/CD pipelines.
    Generates authentic FFmpeg MP4 video clips on the fly.
    """

    def __init__(
        self,
        clip_duration: int = 2,
        auth_required: bool = False,
        simulated_fail_scenes: Optional[List[int]] = None,
    ):
        self.clip_duration = clip_duration
        self.auth_required = auth_required
        self.simulated_fail_scenes = simulated_fail_scenes or []
        self.current_prompt: Optional[str] = None
        self.is_initialized = False

    async def initialize(self) -> None:
        logger.info("[MOCK] Initializing simulated Google Flow environment...")
        await asyncio.sleep(0.1)
        self.is_initialized = True

    async def check_authenticated(self) -> bool:
        if self.auth_required:
            logger.warning("[MOCK] Simulating Google Flow authentication required.")
            return False
        return True

    async def submit_prompt(self, prompt: str) -> None:
        if not self.is_initialized:
            await self.initialize()
        self.current_prompt = prompt
        logger.info(f"[MOCK] Prompt submitted to Google Flow: \"{prompt[:60]}...\"")
        await asyncio.sleep(0.2)

    async def wait_for_generation_started(self, timeout: float = 30.0) -> bool:
        logger.info("[MOCK] Generation started: spinner visible on canvas.")
        await asyncio.sleep(0.2)
        return True

    async def wait_for_generation_completed(self, timeout: float = 300.0, polling_interval: float = 2.0) -> str:
        logger.info(f"[MOCK] Generating ~{self.clip_duration}s video clip...")
        await asyncio.sleep(0.5)
        logger.info("[MOCK] Generation completed: video card rendered on canvas.")
        return "mock_video_asset_id"

    async def download_generated_video(self, target_path: str, timeout: float = 120.0) -> str:
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"[MOCK] Generating synthetic video file for {target.name}...")

        # Use FFmpeg to generate a valid test clip
        cmd = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", f"testsrc=duration={self.clip_duration}:size=640x360:rate=30",
            "-f", "lavfi",
            "-i", f"sine=frequency=440:duration={self.clip_duration}",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(target),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0 or not target.exists() or target.stat().st_size == 0:
            raise FlowDownloadError(f"Failed to generate mock video: {stderr.decode('utf-8', errors='ignore')}")

        logger.info(f"[MOCK] Saved valid video clip: {target.name} ({target.stat().st_size} bytes)")
        return str(target)

    async def close(self) -> None:
        logger.info("[MOCK] Closed simulated Google Flow session.")
