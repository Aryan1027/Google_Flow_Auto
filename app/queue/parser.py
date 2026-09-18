import re
from typing import List, Optional, Tuple
from app.queue.models import SceneItem, SceneStatus, VideoGroup


class PromptParseError(Exception):
    """Raised when prompt parsing fails validation."""
    pass


def parse_prompts(
    text_content: str,
    scenes_per_video: int = 6,
    target_prompts: Optional[int] = 60,
    strict_count: bool = False
) -> Tuple[List[SceneItem], List[VideoGroup]]:
    """
    Parses prompts from either a blank-line separated list or explicit grouped format:
    
    Format A (Explicit):
      VIDEO 01
      Prompt 1
      Prompt 2
      ...
      VIDEO 02
      ...

    Format B (Simple blank-line separated):
      Prompt 1

      Prompt 2
      ...

    Validates:
      - Total prompt count must be divisible by scenes_per_video.
      - If strict_count is True, total prompts must match target_prompts exactly.
      - If missing prompts, raises a descriptive PromptParseError.
    """
    raw_lines = [line.strip() for line in text_content.strip().splitlines()]
    
    # Filter out empty comments if present
    cleaned_lines = []
    for line in raw_lines:
        if line.startswith("#"):
            continue
        cleaned_lines.append(line)

    # Detect if explicit grouped format is used (e.g. "VIDEO 01", "VIDEO 1", "[VIDEO 1]")
    video_header_regex = re.compile(r"^\[?VIDEO\s*(\d+)\]?$", re.IGNORECASE)
    has_headers = any(video_header_regex.match(line) for line in cleaned_lines)

    extracted_prompts: List[str] = []

    if has_headers:
        current_prompts: List[str] = []
        for line in cleaned_lines:
            if not line:
                continue
            if video_header_regex.match(line):
                # Header encountered
                continue
            current_prompts.append(line)
        extracted_prompts = current_prompts
    else:
        # Simple format separated by one or more blank lines
        paragraphs = re.split(r"\n\s*\n+", text_content.strip())
        for p in paragraphs:
            trimmed = p.strip()
            # If paragraph contains multiple lines without blank lines, also split if they look like separate prompts
            lines = [l.strip() for l in trimmed.splitlines() if l.strip() and not l.strip().startswith("#")]
            if len(lines) == 1:
                extracted_prompts.append(lines[0])
            else:
                # If multiple lines in a block, add each line as a prompt
                for l in lines:
                    extracted_prompts.append(l)

    total_loaded = len(extracted_prompts)

    if total_loaded == 0:
        raise PromptParseError("No prompts found in the provided input.")

    remainder = total_loaded % scenes_per_video
    target_count = target_prompts or 60
    target_video_count = target_count // scenes_per_video

    if remainder != 0:
        missing = scenes_per_video - remainder
        raise PromptParseError(
            f"{target_count} prompts required for {target_video_count} complete videos.\n"
            f"Currently loaded: {total_loaded}\n"
            f"Missing: {missing} to complete video {(total_loaded // scenes_per_video) + 1}."
        )

    if strict_count and total_loaded != target_count:
        diff = target_count - total_loaded
        if diff > 0:
            raise PromptParseError(
                f"{target_count} prompts required for {target_video_count} complete videos.\n"
                f"Currently loaded: {total_loaded}\n"
                f"Missing: {diff}"
            )
        else:
            raise PromptParseError(
                f"Expected {target_count} prompts, but received {total_loaded} (excess of {-diff})."
            )

    # Build SceneItems and VideoGroups
    scene_items: List[SceneItem] = []
    video_groups: List[VideoGroup] = []

    total_videos = total_loaded // scenes_per_video
    for v_idx in range(total_videos):
        v_num = v_idx + 1
        group = VideoGroup(video_number=v_num, scenes=[])
        for s_idx in range(scenes_per_video):
            overall_scene_id = (v_idx * scenes_per_video) + s_idx + 1
            scene_num = s_idx + 1
            prompt_text = extracted_prompts[overall_scene_id - 1]

            item = SceneItem(
                scene_id=overall_scene_id,
                video_number=v_num,
                scene_number=scene_num,
                prompt=prompt_text,
                status=SceneStatus.PENDING,
            )
            scene_items.append(item)
            group.scenes.append(item)
        video_groups.append(group)

    return scene_items, video_groups
