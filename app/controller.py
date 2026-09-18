import asyncio
from enum import Enum
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.checkpoint.database import CheckpointDatabase
from app.config import AppConfig
from app.flow.base import BaseFlowBot, FlowAuthenticationError, FlowDownloadError, FlowGenerationError
from app.flow.mock import MockFlowBot
from app.merger.ffmpeg import FFmpegMerger
from app.queue.manager import QueueManager
from app.queue.models import SceneItem, SceneStatus, VideoGroup
from app.utils.logger import logger


class ControllerState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class AutomationController:
    """
    Central orchestrator coordinating the prompt queue, Google Flow browser automation,
    crash recovery, checkpointing, and FFmpeg merging.
    """

    def __init__(self, config: AppConfig, bot: Optional[BaseFlowBot] = None):
        self.config = config
        self.db = CheckpointDatabase(self.config.paths.db_file)
        self.queue = QueueManager(self.db, self.config)
        self.merger = FFmpegMerger(self.config.ffmpeg)
        self.bot = bot
        self.state: ControllerState = ControllerState.IDLE
        self._runner_task: Optional[asyncio.Task] = None
        self._pause_requested = False
        self._stop_requested = False
        self.current_scene: Optional[SceneItem] = None
        self.last_error: Optional[str] = None
        self._state_change_listeners: List[Callable[[str], None]] = []

    def add_state_listener(self, listener: Callable[[str], None]) -> None:
        if listener not in self._state_change_listeners:
            self._state_change_listeners.append(listener)

    def _set_state(self, new_state: ControllerState) -> None:
        self.state = new_state
        for listener in self._state_change_listeners:
            try:
                listener(new_state.value)
            except Exception:
                pass

    def get_bot(self) -> BaseFlowBot:
        """Instantiate bot if not already injected."""
        if self.bot is not None:
            return self.bot

        if self.config.workflow.test_mode:
            self.bot = MockFlowBot()
        else:
            try:
                from app.flow.automation import PlaywrightFlowBot
                self.bot = PlaywrightFlowBot(self.config)
            except Exception as e:
                logger.error(f"Failed to load Playwright bot: {e}. Falling back to Mock bot.")
                self.bot = MockFlowBot()
        return self.bot

    async def start(self) -> None:
        """Start or resume the automation loop."""
        if self.state == ControllerState.RUNNING:
            logger.info("Automation is already running.")
            return

        self._pause_requested = False
        self._stop_requested = False
        self._set_state(ControllerState.RUNNING)
        self._runner_task = asyncio.create_task(self._run_loop())

    async def pause(self) -> None:
        """Gracefully pause after the current safe step."""
        if self.state != ControllerState.RUNNING:
            return
        logger.info("Pause requested. Finishing current safe step...")
        self._pause_requested = True

    async def resume(self) -> None:
        """Resume execution from paused or idle state."""
        if self.state == ControllerState.PAUSED or self.state == ControllerState.IDLE or self.state == ControllerState.AUTH_REQUIRED:
            logger.info("Resuming automation...")
            await self.start()

    async def stop(self) -> None:
        """Stop automation cleanly."""
        logger.info("Stopping automation cleanly...")
        self._stop_requested = True
        self._set_state(ControllerState.STOPPED)
        if self._runner_task and not self._runner_task.done():
            self._runner_task.cancel()
            try:
                await self._runner_task
            except asyncio.CancelledError:
                pass
        self._runner_task = None
        if self.bot:
            await self.bot.close()

    def retry_scene(self, scene_id: int) -> bool:
        """Manually reset a scene to PENDING for retry."""
        return self.queue.manual_retry(scene_id)

    async def _run_loop(self) -> None:
        try:
            # 1. Inspect persisted state & perform crash recovery
            self.db.perform_crash_recovery()

            bot = self.get_bot()
            await bot.initialize()

            # Check authentication
            is_auth = await bot.check_authenticated()
            if not is_auth:
                self._set_state(ControllerState.AUTH_REQUIRED)
                self.last_error = "Google Flow authentication required. Automation paused. Please log in manually and resume."
                logger.warning(self.last_error)
                return

            while not self._stop_requested:
                if self._pause_requested:
                    self._set_state(ControllerState.PAUSED)
                    logger.info("Automation successfully paused.")
                    return

                # Find next incomplete scene
                next_scene = self.queue.get_next_scene()
                if not next_scene:
                    logger.info("All scenes in queue are complete!")
                    # Check any pending video merges
                    self._check_and_merge_completed_videos()
                    self._set_state(ControllerState.COMPLETED)
                    break

                self.current_scene = next_scene
                success = await self._process_single_scene(next_scene)
                if not success:
                    # Check if retry was scheduled or if it completely failed
                    updated = self.db.get_scene(next_scene.scene_id)
                    if updated and updated.status == SceneStatus.FAILED:
                        self._set_state(ControllerState.ERROR)
                        self.last_error = f"Scene {next_scene.scene_id:02d} exceeded maximum retries."
                        logger.error(f"{self.last_error} Queue paused.")
                        return

                # After scene completion, check if its video group is complete and ready to merge
                self._check_and_merge_completed_videos()

                # Delay between operations
                await asyncio.sleep(self.config.flow.delay_between_operations)

        except asyncio.CancelledError:
            logger.info("Automation loop cancelled.")
            self._set_state(ControllerState.STOPPED)
        except FlowAuthenticationError as e:
            self._set_state(ControllerState.AUTH_REQUIRED)
            self.last_error = str(e)
            logger.warning(str(e))
        except Exception as e:
            self._set_state(ControllerState.ERROR)
            self.last_error = str(e)
            logger.error(f"Fatal error in automation loop: {e}", exc_info=True)
        finally:
            self.current_scene = None

    async def _process_single_scene(self, scene: SceneItem) -> bool:
        v_num = scene.video_number
        s_num = scene.scene_number
        s_id = scene.scene_id

        logger.info(f"Starting Video {v_num:02d} / Scene {s_num:02d} (Prompt #{s_id:02d})")
        bot = self.get_bot()

        # Destination path for the clip
        clip_dir = Path(self.config.paths.output_dir) / f"Video_{v_num:02d}"
        clip_dir.mkdir(parents=True, exist_ok=True)
        clip_file_path = str(clip_dir / f"scene_{s_num:02d}.mp4")

        # Check if file already exists from a previous completed step
        if os.path.isfile(clip_file_path) and os.path.getsize(clip_file_path) > 1024:
            logger.info(f"Clip {clip_file_path} already exists on disk. Marking scene COMPLETED.")
            self.queue.mark_completed(s_id, clip_file_path)
            return True

        try:
            # 1. Mark GENERATING & submit prompt
            self.queue.mark_generating(s_id)
            await bot.submit_prompt(scene.prompt)

            # 2. Detect generation start
            await bot.wait_for_generation_started(timeout=30.0)

            # 3. Poll for completion
            await bot.wait_for_generation_completed(
                timeout=self.config.flow.generation_timeout,
                polling_interval=self.config.flow.polling_interval,
            )
            self.queue.mark_generated(s_id)

            # 4. Download video
            self.queue.mark_downloading(s_id)
            final_path = await bot.download_generated_video(
                target_path=clip_file_path,
                timeout=self.config.flow.download_timeout,
            )

            # 5. Mark COMPLETED
            self.queue.mark_completed(s_id, final_path)
            logger.info(f"Scene {s_id:02d} (Video {v_num:02d} Scene {s_num:02d}) successfully completed!")
            return True

        except FlowAuthenticationError:
            raise
        except Exception as e:
            err_msg = str(e)
            logger.warning(f"Error processing Scene {s_id:02d}: {err_msg}")
            self.queue.handle_scene_failure(scene, err_msg)
            return False

    def _check_and_merge_completed_videos(self) -> None:
        """Checks if any video has all 6 scenes downloaded and merges them in exact sequence."""
        video_groups = self.queue.get_video_groups()
        for group in video_groups:
            if self.queue.is_video_ready_for_merge(group.video_number):
                v_num = group.video_number
                logger.info(f"All {len(group.scenes)} scenes complete for Video {v_num:02d}. Merging with FFmpeg...")

                # Exact sorted clip paths: scene_01 -> scene_02 -> ... -> scene_06
                clip_paths = [s.file_path for s in group.scenes if s.file_path]
                out_merged_path = str(
                    Path(self.config.paths.output_dir) / f"Video_{v_num:02d}" / f"Video_{v_num:02d}.mp4"
                )

                try:
                    merged = self.merger.merge_video_scenes(clip_paths, out_merged_path)
                    self.queue.mark_video_merged(v_num, merged)
                    logger.info(f"Successfully generated final merged Video {v_num:02d}: {merged}")
                except Exception as e:
                    logger.error(f"FFmpeg merge failed for Video {v_num:02d}: {e}")

    def get_status_payload(self) -> Dict[str, Any]:
        """Provides a complete real-time status snapshot for the CLI and Web UI."""
        summary = self.queue.get_summary()
        video_groups = self.queue.get_video_groups()

        current_data = None
        if self.current_scene:
            current_data = {
                "scene_id": self.current_scene.scene_id,
                "video_number": self.current_scene.video_number,
                "scene_number": self.current_scene.scene_number,
                "prompt": self.current_scene.prompt,
                "status": self.current_scene.status.value,
                "retry_count": self.current_scene.retry_count,
            }

        return {
            "state": self.state.value,
            "current_scene": current_data,
            "last_error": self.last_error,
            "summary": summary,
            "video_groups": [g.to_dict() for g in video_groups],
        }
