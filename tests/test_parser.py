import pytest
from app.queue.parser import PromptParseError, parse_prompts


def test_parse_sample_file():
    with open("data/prompts_sample.txt", "r", encoding="utf-8") as f:
        content = f.read()

    scenes, video_groups = parse_prompts(content, scenes_per_video=6, target_prompts=60)
    assert len(scenes) == 60
    assert len(video_groups) == 10

    # Verify grouping
    for idx, group in enumerate(video_groups, 1):
        assert group.video_number == idx
        assert len(group.scenes) == 6
        for s_idx, scene in enumerate(group.scenes, 1):
            assert scene.video_number == idx
            assert scene.scene_number == s_idx
            assert scene.scene_id == (idx - 1) * 6 + s_idx


def test_parse_blank_lines_format():
    content = """
    Prompt 1
    
    Prompt 2
    
    Prompt 3
    
    Prompt 4
    
    Prompt 5
    
    Prompt 6
    """
    scenes, video_groups = parse_prompts(content, scenes_per_video=6, target_prompts=60, strict_count=False)
    assert len(scenes) == 6
    assert len(video_groups) == 1
    assert video_groups[0].video_number == 1
    assert scenes[0].prompt == "Prompt 1"
    assert scenes[5].prompt == "Prompt 6"


def test_parse_validation_error_not_divisible_by_six():
    # 58 prompts (missing 2)
    content = "\n\n".join([f"Prompt {i}" for i in range(1, 59)])
    with pytest.raises(PromptParseError) as exc_info:
        parse_prompts(content, scenes_per_video=6, target_prompts=60)

    err_msg = str(exc_info.value)
    assert "60 prompts required for 10 complete videos" in err_msg
    assert "Currently loaded: 58" in err_msg
    assert "Missing: 2" in err_msg


def test_parse_empty_input():
    with pytest.raises(PromptParseError) as exc_info:
        parse_prompts("   \n\n   ")
    assert "No prompts found" in str(exc_info.value)
