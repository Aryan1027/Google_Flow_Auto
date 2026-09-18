import os
import tempfile
import pytest
from app.checkpoint.database import CheckpointDatabase
from app.queue.models import SceneItem, SceneStatus


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = CheckpointDatabase(db_path)
    yield db
    if os.path.exists(db_path):
        os.remove(db_path)


def test_save_and_retrieve_scenes(temp_db):
    scenes = [
        SceneItem(scene_id=1, video_number=1, scene_number=1, prompt="Test 1"),
        SceneItem(scene_id=2, video_number=1, scene_number=2, prompt="Test 2"),
    ]
    temp_db.save_scenes(scenes)

    retrieved = temp_db.get_all_scenes()
    assert len(retrieved) == 2
    assert retrieved[0].prompt == "Test 1"
    assert retrieved[1].prompt == "Test 2"
    assert retrieved[0].status == SceneStatus.PENDING


def test_update_status_and_retries(temp_db):
    scenes = [SceneItem(scene_id=1, video_number=1, scene_number=1, prompt="Test 1")]
    temp_db.save_scenes(scenes)

    temp_db.update_scene_status(1, SceneStatus.GENERATING)
    s = temp_db.get_scene(1)
    assert s.status == SceneStatus.GENERATING

    temp_db.update_scene_status(1, SceneStatus.FAILED, error="Timeout", increment_retry=True)
    s = temp_db.get_scene(1)
    assert s.status == SceneStatus.FAILED
    assert s.retry_count == 1
    assert s.error == "Timeout"


def test_crash_recovery_resets_in_flight_scenes(temp_db):
    scenes = [
        SceneItem(scene_id=1, video_number=1, scene_number=1, prompt="Test 1", status=SceneStatus.COMPLETED, file_path="/fake/nonexistent.mp4"),
        SceneItem(scene_id=2, video_number=1, scene_number=2, prompt="Test 2", status=SceneStatus.GENERATING),
        SceneItem(scene_id=3, video_number=1, scene_number=3, prompt="Test 3", status=SceneStatus.DOWNLOADING),
    ]
    temp_db.save_scenes(scenes)

    reverted, missing = temp_db.perform_crash_recovery()
    assert reverted == 2  # Scene 2 & 3 reset from GENERATING/DOWNLOADING
    assert missing == 1   # Scene 1 reset because nonexistent file

    s1 = temp_db.get_scene(1)
    s2 = temp_db.get_scene(2)
    s3 = temp_db.get_scene(3)

    assert s1.status == SceneStatus.PENDING
    assert s2.status == SceneStatus.PENDING
    assert s3.status == SceneStatus.PENDING


def test_resume_finds_first_incomplete(temp_db):
    scenes = [
        SceneItem(scene_id=1, video_number=1, scene_number=1, prompt="Test 1", status=SceneStatus.COMPLETED),
        SceneItem(scene_id=2, video_number=1, scene_number=2, prompt="Test 2", status=SceneStatus.COMPLETED),
        SceneItem(scene_id=3, video_number=1, scene_number=3, prompt="Test 3", status=SceneStatus.PENDING),
        SceneItem(scene_id=4, video_number=1, scene_number=4, prompt="Test 4", status=SceneStatus.PENDING),
    ]
    temp_db.save_scenes(scenes)

    next_scene = temp_db.get_first_incomplete_scene()
    assert next_scene is not None
    assert next_scene.scene_id == 3
