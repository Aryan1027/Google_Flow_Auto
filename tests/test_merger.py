import os
import subprocess
import tempfile
import pytest
from app.merger.ffmpeg import FFmpegMerger, probe_media


def create_synthetic_clip(out_path: str, duration: int = 1, width: int = 640, height: int = 360) -> str:
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=30",
        "-f", "lavfi",
        "-i", f"sine=frequency=440:duration={duration}",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        out_path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return out_path


def test_ffmpeg_probe_and_merge_six_clips():
    with tempfile.TemporaryDirectory() as tmp_dir:
        clip_paths = []
        for i in range(1, 7):
            p = os.path.join(tmp_dir, f"scene_{i:02d}.mp4")
            create_synthetic_clip(p, duration=1)
            assert os.path.isfile(p)
            clip_paths.append(p)

        # Probe individual clip
        info = probe_media(clip_paths[0])
        assert info["video"]["width"] == 640
        assert info["video"]["height"] == 360
        assert info["video"]["codec"] == "h264"
        assert info["audio"]["codec"] == "aac"
        assert abs(info["duration"] - 1.0) < 0.2

        # Merge clips
        output_file = os.path.join(tmp_dir, "Video_01.mp4")
        merger = FFmpegMerger()
        result = merger.merge_video_scenes(clip_paths, output_file)

        assert os.path.isfile(result)
        assert os.path.getsize(result) > 0

        # Verify merged file properties
        merged_info = probe_media(result)
        assert merged_info["video"]["width"] == 640
        assert merged_info["video"]["height"] == 360
        # 6 clips of 1s each = ~6s
        assert abs(merged_info["duration"] - 6.0) < 0.5
