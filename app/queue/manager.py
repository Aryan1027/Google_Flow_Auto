from typing import Any, Dict, List, Optional
from app.checkpoint.database import CheckpointDatabase
from app.config import AppConfig
from app.queue.models import SceneItem, SceneStatus, VideoGroup
from app.queue.parser import parse_prompts
from app.utils.logger import logger


class QueueManager:
    """Manages the persistent scene queue, retry limits, and transitions."""

    def __init__(self, db: CheckpointDatabase, config: AppConfig):
        self.db = db
        self.config = config

    def load_prompts_from_text(self, text: str, overwrite: bool = False) -> List[SceneItem]:
        scenes, _ = parse_prompts(
            text_content=text,
            scenes_per_video=self.config.workflow.scenes_per_video,
            target_prompts=self.config.workflow.target_prompts,
            strict_count=False,
        )
        self.db.save_scenes(scenes, overwrite=overwrite)
        logger.info(f"Queue loaded: {len(scenes)} prompts ({len(scenes) // self.config.workflow.scenes_per_video} videos)")
        return scenes

    def get_all_scenes(self) -> List[SceneItem]:
        return self.db.get_all_scenes()

    def get_video_groups(self) -> List[VideoGroup]:
        return self.db.get_video_groups(self.config.workflow.scenes_per_video)

    def get_video_group(self, video_number: int) -> Optional[VideoGroup]:
        for g in self.get_video_groups():
            if g.video_number == video_number:
                return g
        return None

    def get_next_scene(self) -> Optional[SceneItem]:
        """Find the next scene that requires processing."""
        return self.db.get_first_incomplete_scene()

    def mark_generating(self, scene_id: int) -> None:
        self.db.update_scene_status(scene_id, SceneStatus.GENERATING)

    def mark_generated(self, scene_id: int) -> None:
        self.db.update_scene_status(scene_id, SceneStatus.GENERATED)

    def mark_downloading(self, scene_id: int) -> None:
        self.db.update_scene_status(scene_id, SceneStatus.DOWNLOADING)

    def mark_completed(self, scene_id: int, file_path: str) -> None:
        self.db.update_scene_status(scene_id, SceneStatus.COMPLETED, file_path=file_path)

    def handle_scene_failure(self, scene: SceneItem, error: str) -> bool:
        """
        Increment retry and check if maximum retries exceeded.
        Returns True if another retry will be attempted, False if marked FAILED.
        """
        new_count = scene.retry_count + 1
        max_retries = self.config.flow.max_retries
        if new_count <= max_retries:
            logger.warning(f"Scene {scene.scene_id:02d} failed ({error}). Retry {new_count}/{max_retries}")
            self.db.update_scene_status(
                scene.scene_id,
                SceneStatus.PENDING,
                error=error,
                increment_retry=True,
            )
            return True
        else:
            logger.error(f"Scene {scene.scene_id:02d} FAILED after {max_retries} retries: {error}")
            self.db.update_scene_status(
                scene.scene_id,
                SceneStatus.FAILED,
                error=error,
                increment_retry=True,
            )
            return False

    def manual_retry(self, scene_id: int) -> bool:
        """User manually requests a retry for a specific scene."""
        scene = self.db.get_scene(scene_id)
        if not scene:
            return False
        logger.info(f"Manual retry triggered for Scene {scene_id:02d}")
        self.db.reset_scene_for_retry(scene_id)
        return True

    def is_video_ready_for_merge(self, video_number: int) -> bool:
        group = self.get_video_group(video_number)
        if not group or not group.scenes:
            return False
        if len(group.scenes) != self.config.workflow.scenes_per_video:
            return False
        return group.is_complete and not group.merged_file_path

    def mark_video_merged(self, video_number: int, merged_file_path: str) -> None:
        self.db.save_video_merged(video_number, merged_file_path)
        logger.info(f"Video {video_number:02d} merge recorded: {merged_file_path}")

    def get_summary(self) -> Dict[str, Any]:
        return self.db.get_progress_summary()
