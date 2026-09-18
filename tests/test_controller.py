import asyncio
import os
import tempfile
import pytest

from app.config import AppConfig
from app.controller import AutomationController, ControllerState
from app.flow.mock import MockFlowBot
from app.queue.models import SceneItem, SceneStatus


@pytest.mark.asyncio
async def test_controller_end_to_end_one_video():
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = AppConfig()
        config.paths.output_dir = os.path.join(tmp_dir, "output")
        config.paths.data_dir = os.path.join(tmp_dir, "data")
        config.paths.logs_dir = os.path.join(tmp_dir, "logs")
        config.paths.db_file = os.path.join(tmp_dir, "data", "test.db")
        config.workflow.test_mode = True
        config.workflow.scenes_per_video = 6
        config.flow.delay_between_operations = 0.05

        bot = MockFlowBot(clip_duration=1)
        controller = AutomationController(config, bot=bot)

        # Load 6 prompts
        prompts = "\n\n".join([f"Test prompt {i} for video 1" for i in range(1, 7)])
        controller.queue.load_prompts_from_text(prompts)

        # Start controller
        await controller.start()

        # Wait for loop to finish
        for _ in range(50):
            await asyncio.sleep(0.2)
            if controller.state == ControllerState.COMPLETED:
                break

        assert controller.state == ControllerState.COMPLETED

        # Check that all 6 scenes are COMPLETED
        scenes = controller.queue.get_all_scenes()
        assert len(scenes) == 6
        assert all(s.status == SceneStatus.COMPLETED for s in scenes)
        assert all(s.file_path and os.path.isfile(s.file_path) for s in scenes)

        # Check merged video exists
        merged_video = os.path.join(config.paths.output_dir, "Video_01", "Video_01.mp4")
        assert os.path.isfile(merged_video)
        assert os.path.getsize(merged_video) > 0


@pytest.mark.asyncio
async def test_controller_resume_preserves_completed():
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = AppConfig()
        config.paths.output_dir = os.path.join(tmp_dir, "output")
        config.paths.data_dir = os.path.join(tmp_dir, "data")
        config.paths.logs_dir = os.path.join(tmp_dir, "logs")
        config.paths.db_file = os.path.join(tmp_dir, "data", "test_resume.db")
        config.workflow.test_mode = True
        config.workflow.scenes_per_video = 6
        config.flow.delay_between_operations = 0.05

        bot = MockFlowBot(clip_duration=1)
        controller = AutomationController(config, bot=bot)

        prompts = "\n\n".join([f"Resume prompt {i}" for i in range(1, 7)])
        controller.queue.load_prompts_from_text(prompts)

        # Pre-create scene 1 and 2 as completed
        vid1_dir = os.path.join(config.paths.output_dir, "Video_01")
        os.makedirs(vid1_dir, exist_ok=True)

        for s_id in (1, 2):
            f_path = os.path.join(vid1_dir, f"scene_{s_id:02d}.mp4")
            await bot.download_generated_video(f_path)
            controller.queue.mark_completed(s_id, f_path)

        # Verify initial resume point
        next_scene = controller.queue.get_next_scene()
        assert next_scene is not None
        assert next_scene.scene_id == 3

        # Start controller and let it finish remaining scenes 3..6
        await controller.start()

        for _ in range(50):
            await asyncio.sleep(0.2)
            if controller.state == ControllerState.COMPLETED:
                break

        assert controller.state == ControllerState.COMPLETED

        # Verify all 6 complete
        scenes = controller.queue.get_all_scenes()
        assert all(s.status == SceneStatus.COMPLETED for s in scenes)

        merged_video = os.path.join(config.paths.output_dir, "Video_01", "Video_01.mp4")
        assert os.path.isfile(merged_video)
